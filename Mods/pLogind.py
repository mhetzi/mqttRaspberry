"""
from pydbus import SystemBus
bus = SystemBus()
proxy = bus.get(".login1", "/org/freedesktop/login1")

proxy.ListSessions()
=> [('c1', 42, 'gdm', 'seat0', '/org/freedesktop/login1/session/c1'),
    ('4', 1000, 'marcel', '', '/org/freedesktop/login1/session/_34'),
    ('2', 1000, 'marcel', 'seat0', '/org/freedesktop/login1/session/_32')]

import os
os.getuid()

import dbus
bus = dbus.SystemBus()
proxy = bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1')
login1 = dbus.Interface(proxy, 'org.freedesktop.login1.Manager')
fd = login1.Inhibit('handle-power-key', 'test_logind', 'test_logind handling power button', 'block').take()

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
from Tools.mqttDevice import Switch, Lock, LockState
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

class Session:
    name: str
    session: dbus.Interface
    isGUI: bool
    _lock: Lock

    def __init__(self, log:logging.Logger, pm: PluginMan.PluginManager, bus_path:str, bus: dbus.SystemBus):
        self._proxy     = bus.get_object('org.freedesktop.login1', bus_path)
        self.session    = dbus.Interface(self._proxy, 'org.freedesktop.login1.Session')
        self.properties = dbus.Interface(self._proxy, 'org.freedesktop.DBus.Properties')
        self.isGUI      = "seat" in self.properties.Get("org.freedesktop.login1.Session", "Seat")[0]
        self.name       = self.properties.Get("org.freedesktop.login1.Session", "Id")
        self.isRemote   = self.properties.Get("org.freedesktop.login1.Session", "Remote")
        self.uname      = self.properties.Get("org.freedesktop.login1.Session", "Name")

        self._log = log.getChild("Session")
        self._pman = pm

    def register(self):
        if self.isGUI:
            self._lock = Lock(
                self._log,
                self._pman,
                self.callback,
                "GUI-Anmeldung {}".format(self.uname),
                unique_id="lock.logind.session.gui.{}.screenlock".format(self.uname)
            )
            self._lock.register()

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
        else:
            self.unloock()

class logindDbus:
    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._bus    = None
        self._proxy  = None
        self._login1 = None
        self._logger = logger
        self._mainloop = None
        self.thread_gml = GlibThread()
        
        self.inhibit_lock = -1
        self._switches = {}
        self.sessions = {}
        self._config = opts
    
    def _setup_dbus_interfaces(self):
        from dbus.mainloop.glib import DBusGMainLoop
        self._mainloop = DBusGMainLoop(set_as_default=True)
        import dbus.mainloop.glib as gml
        gml.threads_init()

        self._bus    = dbus.SystemBus(mainloop=self._mainloop)
        self._proxy  = self._bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1')
        self._login1 = dbus.Interface(self._proxy, 'org.freedesktop.login1.Manager')


    def set_pluginManager(self, pm:PluginMan.PluginManager):
        self._pluginManager = pm

    def register(self):
        self._setup_dbus_interfaces()
        netName = autodisc.Topics.get_std_devInf().name
        # Kann ich ausschalten?
        if self._login1.CanPowerOff() == "yes" and self._config.get("logind/allow_power_off", True):
            self._switches["isOn"] = Switch(
                self._logger,
                self._pluginManager,
                lambda state_requested, message: self.sw_call(userdata="isOn",state_requested=state_requested, message=message),
                name="{} Eingeschaltet".format(netName)
            )
            self._bus.add_signal_receiver(handler_function=self.sendSuspend, signal_name="PrepareForShutdown")
        # Kann ich suspend?
        if self._login1.CanSuspend() == "yes" and self._config.get("logind/allow_suspend", True):
            self._switches["suspend"] = Switch(
                self._logger,
                self._pluginManager,
                lambda state_requested, message: self.sw_call(userdata="suspend",state_requested=state_requested, message=message),
                name="{} Schlafen".format(netName), icon="mdi:sleep"
            )
            self._bus.add_signal_receiver(handler_function=self.sendSuspend, signal_name="PrepareForSleep")
        # Kann ich neustarten?
        if self._login1.CanReboot() == "yes" and self._config.get("logind/allow_reboot", True):
            self._switches["reboot"] = Switch(
                self._logger,
                self._pluginManager,
                lambda state_requested, message: self.sw_call(userdata="reboot",state_requested=state_requested, message=message),
                name="{} Neustarten".format(netName), icon="mdi:restart"
            )
        # Kann ich inhibit
        if self.inhibit( ) > 0 and self._config.get("logind/allow_inhibit", True):
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
        self.thread_gml.start()

    def stop(self):
        self._logger.info("[1/4] Entferne Inhibitation block")
        self.uninhibit( )
        self._logger.info("[2/4] Entferne Inhibtitation delay")
        if self.delay_lock > 0:
            os.close(self.delay_lock)
            self._logger.info("[3/4] Beende Glib MainLoop")
        self.thread_gml.shutdown()
        self._logger.info("[4/4] Warten auf Glib MainLoop")
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
            return self._switches["suspend"].turnOn()
        self._switches["suspend"].turnOff()

    def sendShutdown(self, sig):
        if int(sig) == 1:
            self._switches["suspend"].turnOff()
            return self._pluginManager.shutdown()
        self._switches["suspend"].turnOn()

    def sw_call(self, userdata=None, state_requested=False, message=None):
        if state_requested:
            if userdata == "isOn":
                self._switches["isOn"].turnOn()
            elif userdata == "suspend":
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

    def configure(self, conf: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        conf["logind/allow_power_off"] = ConsoleInputTools.get_bool_input("Erlaube Ausschalten: ", True)
        conf["logind/allow_suspend"] = ConsoleInputTools.get_bool_input("Erlaube Bereitschaftsmodus: ", True)
        conf["logind/allow_reboot"] = ConsoleInputTools.get_bool_input("Erlaube Neustarten: ", True)
        conf["logind/allow_inhibit"] = ConsoleInputTools.get_bool_input("Erlaube Blockieren von Schlafmodus: ", True)


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