"""
Könnte sein dass es nur als Benutzerservice (systemctl --user) funktioniert!
Could be that this Plugin only works when run as user service (systemctl --user)!
"""
try:
    import dbus
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('dbus-python', throw=ie, ask=True)
    except err.RestartError:
        import dbus

import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import Tools.PluginManager as PluginMan
from Tools.Devices.Lock import Switch, Lock, LockState
from Tools.Devices.BinarySensor import BinarySensor
import logging
import schedule
import json
import os
import threading
import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib

class GlibThread(threading.Thread):

    def __init__(self):
        super().__init__(name="logind_ml", daemon=False)
        self.loop = GLib.MainLoop()

    def run(self):
        self.loop.run()
    
    def shutdown(self):
        self.loop.quit()

class IdleMonitor:
    _idle_watch_id = None

    def __init__(self, interval:int, log:logging.Logger, pm: PluginMan.PluginManager, bus: dbus.SystemBus, netName="E_NOTSET"):
        self._log  = log.getChild("Mutter.IdleMonitor")
        self._timeout = interval

        self._bsensor = BinarySensor(self._log, pm, "{} AFK".format(netName), autodisc.BinarySensorDeviceClasses.OCCUPANCY, "")

        self.proxy     = bus.get_object('org.gnome.Mutter.IdleMonitor', '/org/gnome/Mutter/IdleMonitor/Core')
        self.idlemon   = dbus.Interface(self.proxy, "org.gnome.Mutter.IdleMonitor")

        self._idle_watch_id = self.idlemon.AddIdleWatch(interval)
        self._active_watch_id = self.idlemon.AddUserActiveWatch()

        self.idlemon.connect_to_signal("WatchFired", self.isIdle)      

    def stop(self):
        if self._idle_watch_id is not None:
            self.idlemon.RemoveWatch(self._idle_watch_id)
        if self._active_watch_id is not None:
            self.idlemon.RemoveWatch(self._active_watch_id)
        self._bsensor.turnOff()
    
    def register(self):
        self._bsensor.register()
        idleing = self.idlemon.GetIdletime()
        if idleing > self._timeout:
            self._bsensor.turnOff()
        else:
            self._bsensor.turnOn()

    def isIdle(self, id):
        self._log.debug("isIdle: ID: {}".format(id))
        if id == self._idle_watch_id:
            self._bsensor.turnOff()
            if self._active_watch_id is not None:
                self.idlemon.RemoveWatch(self._active_watch_id)
            self._active_watch_id = self.idlemon.AddUserActiveWatch()
        elif id == self._active_watch_id:
            self._bsensor.turnOn()
            if self._active_watch_id is not None:
                self.idlemon.RemoveWatch(self._active_watch_id)
            self._active_watch_id = None




class Session:
    name = ""
    session = None
    isGUI = False
    _lock = None

    def __init__(self, log:logging.Logger, pm: PluginMan.PluginManager, bus_path:str, bus: dbus.SystemBus):
        self._proxy     = bus.get_object('org.freedesktop.login1', bus_path)
        self.session    = dbus.Interface(self._proxy, 'org.freedesktop.login1.Session')
        self.properties = dbus.Interface(self._proxy, 'org.freedesktop.DBus.Properties')
        self.isGUI      = "seat" in self.properties.Get("org.freedesktop.login1.Session", "Seat")[0]
        self.name       = self.properties.Get("org.freedesktop.login1.Session", "Id")
        self.isRemote   = self.properties.Get("org.freedesktop.login1.Session", "Remote")
        self.uname      = self.properties.Get("org.freedesktop.login1.Session", "Name")
        self.uID        = self.properties.Get("org.freedesktop.login1.Session", "User")

        self._log = log.getChild("Session")
        self._pman = pm

        self._lock_notify   = None
        self._unlock_notify = None

    def register(self):
        if self.isGUI and self.uID[0] == os.getuid():
            self._lock = Lock(
                self._log,
                self._pman,
                self.callback,
                "GUI-Anmeldung {}".format(self.uname),
                unique_id="lock.logind.session.gui.{}.screenlock".format(self.uname)
            )
            self._lock.register()

            self._lock_notify = self.session.connect_to_signal("Lock",   self._lock.lock)
            self._unlock_notify  = self.session.connect_to_signal("Unlock", self._lock.unlock)
    
    def stop(self):
        if self._lock_notify is not None:
            self._lock_notify.remove()
        if self._unlock_notify is not None:
            self._unlock_notify.remove()

    def terminate(self):
        self.session.Terminate()
    
    def lock(self):
        self._log.info("OK Locking session")
        self.session.Lock()

    def unloock(self):
        self._log.info("OK Unlocking session")
        self.session.Unlock()
    
    def callback(self, state_requested=False, message=LockState.LOCK):
        if message == LockState.LOCK:
            self.lock()
        elif message == LockState.UNLOCK:
            self.unloock()
        else:
            self._log.warning("LockState Requested, but it´s invalid.")

class logindDbus:
    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._bus    = None
        self._proxy  = None
        self._login1 = None
        self._logger = logger
        self._mainloop = None
        self.thread_gml = GlibThread()
        
        self.sleeping = False
        self.shutdown = False

        self.inhibit_lock = -1
        self._switches = {}
        self.sessions = {}
        self._config = conf.PluginConfig(opts, "logind")

        self._poff_notiy  = None
        self._sleep_notiy = None
        self._nsess_notiy = None
        self._rsess_notiy = None
        self._idle_monitor = None
    
    def _setup_dbus_interfaces(self):
        from dbus.mainloop.glib import DBusGMainLoop
        self._mainloop = DBusGMainLoop(set_as_default=True)
        import dbus.mainloop.glib as gml
        gml.threads_init()

        self._bus    = dbus.SystemBus(mainloop=self._mainloop)
        self._session_bus = dbus.SessionBus(mainloop=self._mainloop)
        self._proxy  = self._bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1')
        self._login1 = dbus.Interface(self._proxy, 'org.freedesktop.login1.Manager')

        self._sleep_notiy = self._login1.connect_to_signal("PrepareForSleep", lambda x: self._notify_sleep(sleep=x))
        self._poff_notiy  = self._login1.connect_to_signal("PrepareForShutdown", lambda x: self._notify_sleep(shutdown=x))

        self._nsess_notiy = self._login1.connect_to_signal("SessionNew",     lambda sID, path: self._mod_session(add=True,  path=path) )
        self._rsess_notiy = self._login1.connect_to_signal("SessionRemoved", lambda sID, path: self._mod_session(add=False, path=path) )
        
        for session in self._login1.ListSessions():
            self._logger.info("Neue Benutzersession gefunden {} auf {} in Pfad {}.".format(session[2], session[3], session[4]))
            self._mod_session(add=True, path=session[4])
        
        if self._config.get("inactivity_ms", None) is not None: 
            self._idle_monitor = IdleMonitor(
                self._config["inactivity_ms"],
                self._logger,
                self._pluginManager,
                self._session_bus,
                netName=autodisc.Topics.get_std_devInf().name if self._config.get("custom_name", None) is None else self._config.get("custom_name", None)
            )
        
    
    def _mod_session(self, add=True, path=str):
        if path in self.sessions.keys():
            self.sessions[path].stop()
            del self.sessions[path]
        if add:
            self.sessions[path] = Session(self._logger, self._pluginManager, path, self._bus)
            self.sessions[path].register()

    def _notify_sleep(self, sleep=False, shutdown=False):
        self.sleeping = sleep
        self.shutdown = shutdown
        self.sw_call(userdata="suspend", state_requested=True)
        self.sw_call(userdata="isOn", state_requested=True)
        if self._idle_monitor is not None:
            self._idle_monitor.stop()

    def set_pluginManager(self, pm:PluginMan.PluginManager):
        self._pluginManager = pm

    def register(self, wasConnected=False):
        self._setup_dbus_interfaces()
        netName = autodisc.Topics.get_std_devInf().name if self._config.get("custom_name", None) is None else self._config.get("custom_name", None)
        # Kann ich ausschalten?
        if self._login1.CanPowerOff() == "yes" and self._config.get("allow_power_off", True):
            self._switches["isOn"] = Switch(
                self._logger,
                self._pluginManager,
                lambda state_requested, message: self.sw_call(userdata="isOn",state_requested=state_requested, message=message),
                name="{} Eingeschaltet".format(netName)
            )
            self._bus.add_signal_receiver(handler_function=self.sendSuspend, signal_name="PrepareForShutdown")
        # Kann ich suspend?
        if self._login1.CanSuspend() == "yes" and self._config.get("allow_suspend", True):
            self._switches["suspend"] = Switch(
                self._logger,
                self._pluginManager,
                lambda state_requested, message: self.sw_call(userdata="suspend",state_requested=state_requested, message=message),
                name="{} Schlafen".format(netName), icon="mdi:sleep"
            )
            self._bus.add_signal_receiver(handler_function=self.sendSuspend, signal_name="PrepareForSleep")
        # Kann ich neustarten?
        if self._login1.CanReboot() == "yes" and self._config.get("allow_reboot", True):
            self._switches["reboot"] = Switch(
                self._logger,
                self._pluginManager,
                lambda state_requested, message: self.sw_call(userdata="reboot",state_requested=state_requested, message=message),
                name="{} Neustarten".format(netName), icon="mdi:restart"
            )
        # Kann ich inhibit
        if self.inhibit( ) > 0 and self._config.get("allow_inhibit", True):
            self.uninhibit( )
            self._switches["inhibit"] = Switch(
                self._logger,
                self._pluginManager,
                lambda state_requested, message: self.sw_call(userdata="inhibit",state_requested=state_requested, message=message),
                name="{} Nicht schlafen".format(netName), icon="mdi:sleep-off"
            )
        
        self._switches["isOn"].register()
        self._switches["suspend"].register()
        self._switches["reboot"].register()
        self._switches["inhibit"].register()

        self.delay_lock = self._login1.Inhibit(
            'sleep:shutdown',
            'mqttScript',
            'Publish Powerstatus to Network',
            'delay'
            ).take()

        if self._idle_monitor is not None:
            self._idle_monitor.register()

        if not wasConnected:
            self.thread_gml.start()

    def stop(self):
        self._logger.info("[1/6] Entferne Inhibitation block")
        self.uninhibit( )
        self._logger.info("[2/6] Entferne Inhibtitation delay")
        if self.delay_lock > 0:
            os.close(self.delay_lock)
        self._logger.info("[3/6] Signale werden entfernt")
        if self._poff_notiy is not None:
            self._poff_notiy.remove()
        if self._sleep_notiy is not None:
            self._sleep_notiy.remove()
        for k in self.sessions.keys():
            session= self.sessions[k]
            session.stop()
        if self._nsess_notiy is not None:
            self._nsess_notiy.remove()
        if self._rsess_notiy is not None:
            self._rsess_notiy.remove()

        if self._idle_monitor is not None:
            self._logger.info("[4/6] IdleMonitor entfernt Signale und Watches...")
            self._idle_monitor.stop()

        self._logger.info("[5/6] Beende Glib MainLoop")
        self.thread_gml.shutdown()
        self._logger.info("[6/6] Warten auf Glib MainLoop")
        self.thread_gml.join()

    
    def inhibit(self):
        if self.inhibit_lock > 1:
            return self.inhibit_lock
        self.inhibit_lock = self._login1.Inhibit(
            'sleep:shutdown',
            'mqttScript',
            'Inhibation requested from Network',
            'block'
            ).take()
        return self.inhibit_lock
    
    def uninhibit(self):
        if self.inhibit_lock > 1:
            os.close(self.inhibit_lock)
        self.inhibit_lock = -1

    def findGraphicalSession(self) -> str:
        uid = os.getuid()
        arr = self._login1.ListSessions()
        for a in arr:
            if uid == a[1] and "seat" in a[4]:
                return str(a[0])
    
    def lockGraphicSession(self):
        session_id = self.findGraphicalSession()
        self._login1.LockSession(session_id)

    def unlockGraphicSession(self):
        session_id = self.findGraphicalSession()
        self._login1.UnlockSession(session_id)

    def sendSuspend(self, sig):
        if int(sig) == 1:
            self._idle_monitor.stop()
            return self._switches["suspend"].turnOn()
        self._switches["suspend"].turnOff()

    def sendShutdown(self, sig):
        if int(sig) == 1:
            self._switches["isOn"].turnOff()
            self._idle_monitor.stop()
            return self._pluginManager.shutdown()
        self._switches["isOn"].turnOn()

    def sw_call(self, userdata=None, state_requested=False, message=None):
        if state_requested:
            if userdata == "isOn":
                if self.shutdown or self.sleeping:
                    self._switches["isOn"].turnOff()
                else:
                    self._switches["isOn"].turnOn()
            elif userdata == "suspend":
                if self.sleeping:
                    self._switches["suspend"].turnOn()
                else:    
                    self._switches["suspend"].turnOff()
            elif userdata == "reboot":
                self._switches["reboot"].turnOff()
            elif userdata == "inhibit":
                if self.inhibit_lock > 0:
                    self._switches["inhibit"].turnOn()
                else:
                    self._switches["inhibit"].turnOff()
            return
        msg = message.payload.decode('utf-8')
        if userdata == "isOn" and msg == "OFF":
            self._login1.PowerOff(True)
            self._switches["isOn"].turnOff()
        elif userdata == "suspend" and msg == "ON":
            self._login1.Suspend(True)
        elif userdata == "reboot" and msg == "ON": 
            self._login1.Reboot(True)
        elif userdata == "inhibit" and msg == "ON":
            if self.inhibit_lock < 1:
                self.inhibit()
            if self.inhibit_lock > 0:
                self._switches["inhibit"].turnOn()
        elif userdata == "inhibit" and msg == "OFF":
            if self.inhibit_lock > 0:
                self.uninhibit()
            if self.inhibit_lock < 1:
                self._switches["inhibit"].turnOff()
            

class logindConfig:
    def __init__(self):
        pass

    def configure(self, conff: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        conf = conf.PluginConfig(conff, "logind")

        conf["allow_power_off"] = ConsoleInputTools.get_bool_input("\nErlaube Ausschalten: ", True)
        conf["allow_suspend"] = ConsoleInputTools.get_bool_input("\nErlaube Bereitschaftsmodus: ", True)
        conf["allow_reboot"] = ConsoleInputTools.get_bool_input("\nErlaube Neustarten: ", True)
        conf["allow_inhibit"] = ConsoleInputTools.get_bool_input("\nErlaube Blockieren von Schlafmodus: ", True)
        if ConsoleInputTools.get_bool_input("\nBenutze anderen Namen: ", True):
            conf["custom_name"] = ConsoleInputTools.get_input("\nDen Namen Bitte: ", True)
        conf["inactivity_ms"] = ConsoleInputTools.get_number_input("\nInaktivität nach x Millisekunden: ")


class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "logind"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return logindDbus(client, opts, logger.getChild("logind"), device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        logindConfig().configure(conf, logger.getChild("logind"))