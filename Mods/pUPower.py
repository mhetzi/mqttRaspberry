"""
Könnte sein dass es nur als Benutzerservice (systemctl --user) funktioniert!
Could be that this Plugin only works when run as user service (systemctl --user)!
"""
from typing import IO, Union
import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
from Tools import PluginManager
from Tools.Devices.BinarySensor import BinarySensor
from Tools.Devices.Sensor import Sensor, SensorDeviceClasses
from Tools.Devices.Filters import BlockNotChanged
import logging
import schedule
import json
import os
import threading

from time import sleep

try:
    import dasbus

    from dasbus.connection import SystemMessageBus
    from dasbus.connection import SessionMessageBus

    import Mods.linux.dbus_common

    class Device:
        name = ""
        session = None
        _sensor = None

        def __init__(self, log:logging.Logger, pm: PluginManager.PluginManager, bus_path:str, bus: SystemMessageBus):
            self._proxy     = bus.get_proxy('org.freedesktop.UPower', bus_path)

            self.name = self._proxy.Get("org.freedesktop.UPower.Device", "Model").get_string()
            l = len(self.name)
            if l < 3:
                self.name = self._proxy.Get("org.freedesktop.UPower.Device", "NativePath").get_string()
            
            self._log = log.getChild("Device")
            self._pman = pm

        def _process_prop_changed(self, src, dic, arr, force_send=False):
            state = {
                "soc": self._proxy.Get("org.freedesktop.UPower.Device", "Percentage").get_double(),
                "capaciy": self._proxy.Get("org.freedesktop.UPower.Device", "Capacity").get_double(),
                "NativePath": self._proxy.Get("org.freedesktop.UPower.Device", "NativePath").get_string(),
                "Serial": self._proxy.Get("org.freedesktop.UPower.Device", "Serial").get_string()
            }
            if self._sensor is None:
                return None
            return self._sensor.state(state, force_send, keypath="soc")

        def register(self):
                self._sensor = Sensor(
                    self._log,
                    self._pman,
                    self.name,
                    SensorDeviceClasses.BATTERY,
                    "%",
                    json_attributes=True,
                    unique_id=f"lock.upower.device.{self.name}",
                    value_template="{{value_json.soc}}"
                )
                self._sensor._ignored_counter = 0
                self._sensor.register()

                self._proxy.PropertiesChanged.connect( self._process_prop_changed )
                self._process_prop_changed(None, None, None, True)
        
        def stop(self):
            pass

        def resend(self):
            if self._sensor is None:
                self.register()
                return
            self._sensor.register()
            self._process_prop_changed(None, None, None, True)

    class uPowerDbus(PluginManager.PluginInterface):
        _sleep_delay_lock: Union[IO, None] = None

        def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
            self._bus    = None
            self._proxy  = None
            self._upower = None
            self._logger = logger
            self._mainloop = None
            #self.thread_gml = GlibThread.getThread()
            self._glib_thread = None

            self.sessions: dict[str, Device] = {}
            self._config = conf.PluginConfig(opts, PluginLoader.getConfigKey())

        
        def _setup_dbus_interfaces(self):
            self._glib_thread = Mods.linux.dbus_common.init_dbus()

            self._logger.debug("Getting dbus busses...")
            self._bus    = SystemMessageBus()
            self._session_bus = SessionMessageBus()
            self._proxy  = self._bus.get_proxy('org.freedesktop.UPower', '/org/freedesktop/UPower')

            self._logger.debug("Subscribing to dbus notifications...")
            self._nsess_notiy = self._proxy.DeviceAdded(   lambda sID, path: self._mod_device(add=True,  path=path) )
            self._rsess_notiy = self._proxy.DeviceRemoved( lambda sID, path: self._mod_device(add=False, path=path) )
            
            for session in self._proxy.EnumerateDevices():
                self._logger.info("Neues Upower Gerät auf {} gefunden.".format(session))
                try:
                    self._mod_device(add=True, path=session)
                except:
                    self._logger.exception("Hinzufügen von Gerät fehlgeschlagen!")
            
        
        def _mod_device(self, add=True, path=""):
            if path in self.sessions.keys():
                self.sessions[path].stop()
                del self.sessions[path]
            if add:
                dev = Device(self._logger, self._pluginManager, path, self._bus)
                self.sessions[path] = dev
                self.sessions[path].register()

        def set_pluginManager(self, pm:PluginManager.PluginManager):
            self._pluginManager = pm

        def register(self, wasConnected=False):
            if self._glib_thread is None:
                self._logger.debug("Was registered. Destroy old stuff...")
                self.stop()

            self._logger.debug("Register dbus interface...")
            self._setup_dbus_interfaces()
            self.sendStates()

        def sendStates(self):
            for dev in self.sessions.values():
                dev.resend()
            return super().sendStates()

        def stop(self):
            self._logger.info("[1/3] Signale werden entfernt")
            if self._nsess_notiy is not None:
                self._nsess_notiy.remove()
            if self._rsess_notiy is not None:
                self._rsess_notiy.remove()

            self._logger.info("[2/3] Geräte werden entfernt")
            for k in self.sessions.keys():
                session= self.sessions[k]
                session.stop()

            self._logger.info("[3/3] GLib MainThread stop")
            if self._glib_thread is not None:
                Mods.linux.dbus_common.deinit_dbus()

except ImportError as ie:
    pass            


class uPowerConfig:
    def __init__(self):
        pass

    def configure(self, bc: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        c = conf.PluginConfig(bc, "uPower")
        c["_"] = "" 


class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "uPower"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return uPowerDbus(client, opts, logger.getChild(PluginLoader.getConfigKey()), device_id)

    @staticmethod
    def runConfig(bc: conf.BasicConfig, logger:logging.Logger):
        uPowerConfig().configure(bc, logger.getChild("logind"))
    
    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import dasbus
        except ImportError as ie:
            return ["dasbus"]
        return []