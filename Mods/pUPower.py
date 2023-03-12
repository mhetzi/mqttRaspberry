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

from typing import IO, Union
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

from time import sleep
from Mods.linux.dbus_common import init_dbus

class IdleMonitor:
    _idle_watch_id = None
    _register_delay_id = None
    _IdelingPolling = None
    _is_idle  = False
    __sheduler_fails = 0

    def __init__(self, interval:int, log:logging.Logger, pm: PluginMan.PluginManager, bus: dbus.SystemBus, netName="E_NOTSET"):
        self._log  = log.getChild("Mutter.IdleMonitor")
        self._timeout = interval

        self._bsensor = BinarySensor(self._log, pm, "{} AFK".format(netName), autodisc.BinarySensorDeviceClasses.OCCUPANCY, "")

        self._bus      = bus
        self.proxy     = None
        self.idlemon   = None

        self._idle_watch_id   = None
        self._active_watch_id = None

    def stop(self):
        if self._IdelingPolling is not None:
            schedule.cancel_job(self._IdelingPolling)
        if self._register_delay_id is not None:
            schedule.cancel_job(self._register_delay_id)
        if self._idle_watch_id is not None:
            self.idlemon.RemoveWatch(self._idle_watch_id)
        if self._active_watch_id is not None:
            self.idlemon.RemoveWatch(self._active_watch_id)
        self._bsensor.turnOff()
    
    def _delayed_register(self):
        try:
            self.proxy     = self._bus.get_object('org.gnome.Mutter.IdleMonitor', '/org/gnome/Mutter/IdleMonitor/Core')
            self.idlemon   = dbus.Interface(self.proxy, "org.gnome.Mutter.IdleMonitor")

            self._idle_watch_id = self.idlemon.AddIdleWatch(self._timeout)
            self._active_watch_id = self.idlemon.AddUserActiveWatch()

            self.idlemon.connect_to_signal("WatchFired", self.isIdle)   

            self._bsensor.register()
            idleing = self.idlemon.GetIdletime()
            if idleing > self._timeout:
                self._bsensor.turnOff()
                self._is_idle = True
            else:
                self._bsensor.turnOn()
                self._is_idle = False
            if self._register_delay_id is not None:
                schedule.cancel_job(self._register_delay_id)
            
            if self._IdelingPolling is not None:
                schedule.cancel_job(self._IdelingPolling)
            self._IdelingPolling = schedule.every(2).minutes.do(self.isIdleDead)
        except dbus.exceptions.DBusException:
            self._log.warning("DBus Signale von Mutter verbinden fehlgeschlagen! Wird in 30 Sekunden erneut probiert,,,")
            pass

    def register(self):
        if self._register_delay_id is not None:
            schedule.cancel_job(self._register_delay_id)
        self._register_delay_id = schedule.every(30).seconds.do(self._delayed_register)
        self._register_delay_id.run()


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
        self.lockedHint = self.properties.Get("org.freedesktop.login1.Session", "LockedHint")

        self._log = log.getChild("Session")
        self._pman = pm

        self._lock_notify   = None
        self._unlock_notify = None

    def _process_prop_changed(self, src, dic, arr):
        self.lockedHint: dbus.Boolean = self.properties.Get("org.freedesktop.login1.Session", "LockedHint")
        if self.lockedHint:
            self._lock.lock()
        else:
            self._lock.unlock()

    def is_present(self):
        return True

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

            self._lock_notify    = self.session.connect_to_signal("Lock",   self._lock.lock  )
            self._unlock_notify  = self.session.connect_to_signal("Unlock", self._lock.unlock)
            self.properties.connect_to_signal("PropertiesChanged", self._process_prop_changed)
            self._process_prop_changed(None, None, None)
    
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

class uPowerDbus(PluginMan.PluginInterface):
    _sleep_delay_lock: Union[IO, None] = None

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._bus    = None
        self._proxy  = None
        self._upower = None
        self._logger = logger
        self._mainloop = None
        #self.thread_gml = GlibThread.getThread()

        self.sessions = {}
        self._config = conf.PluginConfig(opts, PluginLoader.getConfigKey())

    
    def _setup_dbus_interfaces(self):
        init_dbus()

        self._bus    = dbus.SystemBus(mainloop=self._mainloop)
        self._session_bus = dbus.SessionBus(mainloop=self._mainloop)
        self._proxy  = self._bus.get_object('org.freedesktop.UPower', '/org/freedesktop/UPower')
        self._upower = dbus.Interface(self._proxy, 'org.freedesktop.UPower')

        self._nsess_notiy = self._upower.connect_to_signal("DeviceAdded",     lambda sID, path: self._mod_session(add=True,  path=path) )
        self._rsess_notiy = self._upower.connect_to_signal("DeviceRemoved", lambda sID, path: self._mod_session(add=False, path=path) )
        
        for session in self._upower.EnumerateDevices():
            self._logger.info("Neues Upower Gerät auf {} gefunden.".format(session))
            self._mod_session(add=True, path=session)
        
    
    def _mod_session(self, add=True, path=""):
        if path in self.sessions.keys():
            self.sessions[path].stop()
            del self.sessions[path]
        if add:
            dev = Session(self._logger, self._pluginManager, path, self._bus)
            if not dev.is_present():
                return
            self.sessions[path] = dev
            self.sessions[path].register()

    def set_pluginManager(self, pm:PluginMan.PluginManager):
        self._pluginManager = pm

    def register(self, wasConnected=False):
        self._setup_dbus_interfaces()
        
        sleep(5.0)


        #if not wasConnected:
        #    self.thread_gml.safe_start()

    def sendStates(self):
        return super().sendStates()

    def stop(self):
        self._logger.info("[1/6] Signale werden entfernt")
        if self._nsess_notiy is not None:
            self._nsess_notiy.remove()
        if self._rsess_notiy is not None:
            self._rsess_notiy.remove()


        self._logger.info("[2/6] Geräte werden entfernt")
        for k in self.sessions.keys():
            session= self.sessions[k]
            session.stop()
        #self._logger.info("[3/6] Beende Glib MainLoop")
        #self.thread_gml.shutdown()
        #try:
        #    self._logger.info("[6/6] Warten auf Glib MainLoop")
        #    self.thread_gml.join()
        #except:
        #    self._logger.debug("Glib MainLoop join failed!")
            

class uPowerConfig:
    def __init__(self):
        pass

    def configure(self, conff: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        conf = conff.PluginConfig(conff, "logind")

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
        return "uPower"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return uPowerDbus(client, opts, logger.getChild(PluginLoader.getConfigKey()), device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        uPowerConfig().configure(conf, logger.getChild("logind"))