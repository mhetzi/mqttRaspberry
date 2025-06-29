"""
Könnte sein dass es nur als Benutzerservice (systemctl --user) funktioniert!
Could be that this Plugin only works when run as user service (systemctl --user)!
"""

import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
from Tools import PluginManager

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "systemd"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        try:
            import dasbus
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('dasbus', throw=ie, ask=False)
        return systemdDbus(client, opts, logger.getChild(PluginLoader.getConfigKey()), device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        systemdConfig().configure(conf, logger.getChild(PluginLoader.getConfigKey()))
    
    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import dasbus
        except ImportError as ie:
            return ["dasbus"]
        return []

from typing import IO, Union
import Tools.Autodiscovery as autodisc
from Tools.Devices.Button import Button
from Tools.Devices.Switch import Switch
from Tools.Devices.BinarySensor import BinarySensor
import schedule
import json
import os
import threading
#try:
#    import gi
#    gi.require_version('GLib', '2.0')
#    from gi.repository import GLib
#except Exception as e:
#    logging.exception(e)
#    pass

try:
    import dasbus

    from dasbus.connection import SystemMessageBus
    from dasbus.connection import SessionMessageBus
    from dasbus.error import DBusError

    import Mods.linux.dbus_common

    from time import sleep

    class SystemdUnit:
        _path = ""
        _unit = ""
        _proxy = None
        
        ActiveState = ""
        SubState = ""
        UnitFileState = ""
        
        _button: Button | None = None
        _switch: Switch | None = None

        def __init__(self, path: str, unit: str, bus: SystemMessageBus, logger: logging.Logger) -> None:
            self._logger = logger
            self._path = path
            self._unit = unit
            self._proxy = bus.get_proxy('org.freedesktop.systemd1', path, "org.freedesktop.systemd1.Unit")
            self._proxy_prop = bus.get_proxy('org.freedesktop.systemd1', path, "org.freedesktop.DBus.Properties")
            self._proxy_prop.PropertiesChanged.connect( self._process_prop_changed )


        def _process_prop_changed(self, src, dic, arr):
            self.ActiveState    = self._proxy_prop.Get("org.freedesktop.systemd1.Unit", "ActiveState"   ).get_string()
            self.SubState       = self._proxy_prop.Get("org.freedesktop.systemd1.Unit", "SubState"      ).get_string()
            self.UnitFileState  = self._proxy_prop.Get("org.freedesktop.systemd1.Unit", "UnitFileState" ).get_string()

            if self._switch is not None:
                self._switch.turn({
                    "s": "ON" if self.SubState == "running" else "OFF",
                    "SubState":  self.SubState,
                    "ActiveState":  self.ActiveState,
                    "UnitFileState": self.UnitFileState
                })

        def button_press(self, message):
            msg = message.payload.decode('utf-8')
            self._logger.debug(f"Button message: {msg} !")
            if msg == "p":
                self._proxy.Restart("replace")

        def switch_toggle(self, state_requested=False, message=None):
            if message is not None:
                msg = message.payload.decode('utf-8')
                try:
                    if msg == "OFF":
                        self._proxy.Stop("replace")
                    elif msg == "ON":
                        self._proxy.Start("replace")
                except DBusError:
                    self._logger.exception("Setting Systemd Unit failed.")

        def register(self, plugin_manager: PluginManager.PluginManager):
            if self._button is None:
                self._button = Button(
                    logger=self._logger,
                    pman=plugin_manager,
                    callback=self.button_press,
                    name=self._unit
                )
            if self._button is not None:
                self._button.register()

            if self._switch is None:
                self._switch = Switch(
                    logger=self._logger,
                    pman=plugin_manager,
                    callback=self.switch_toggle,
                    name=self._unit,
                    json_attributes=True,
                    value_template="{{ value_json.s }}", 
                )
            if self._switch is not None:
                self._switch.register()

            self._process_prop_changed(None, None, None)
        
        def resend(self):
            if self._switch is not None:
                self._switch.resend()

    class systemdDbus:

        def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
            self._bus    = None
            self._proxy  = None
            self._logger = logger
            self._mainloop = None
            
            self._glib_thr = Mods.linux.dbus_common.init_dbus(logger=logger)

            self._units: dict[str, SystemdUnit] = {}
            self._config = conf.PluginConfig(opts, PluginLoader.getConfigKey())
        
        def _setup_dbus_interfaces(self):
            self._bus    = SystemMessageBus()
            self._session_bus = SessionMessageBus()
            self._proxy  = self._bus.get_proxy('org.freedesktop.systemd1', '/org/freedesktop/systemd1')
            self._manager_proxy = self._bus.get_proxy('org.freedesktop.systemd1', '/org/freedesktop/systemd1', "org.freedesktop.systemd1.Manager")

        def loadUnit(self, unit_name: str) -> SystemdUnit | None:
            if self._bus is not None:
                try:
                    self._logger.info(f"Try to load Unit {unit_name}...")
                    up = self._manager_proxy.LoadUnit(unit_name)
                    return self.createUnit(unit_name, up, try_load=False)
                except:
                    self._logger.exception(f"Loading of Unit {unit_name} failed!")
            return None

        def createUnit(self, unit_name, unit_path=None, try_load=True) -> SystemdUnit | None:
            if self._bus is not None:
                try:
                    self._logger.debug(f"Create Unit: {unit_name}")
                    if unit_path is None:
                        unit_path = self._manager_proxy.GetUnit(unit_name)
                    return SystemdUnit(path=unit_path, unit=unit_name, bus=self._bus, logger=self._logger.getChild(unit_name))
                except Exception:
                    if not try_load:
                        self._logger.exception(f"Creating Unit: {unit_name} failed!")
                    if try_load:
                        return self.loadUnit(unit_name)
                    return None
            return None

        def set_pluginManager(self, pm:PluginManager.PluginManager):
            self._pluginManager = pm

        def register(self, wasConnected=False):
            if not wasConnected:
                self._setup_dbus_interfaces()
                netName = autodisc.Topics.get_std_devInf().name if self._config.get("custom_name", None) is None else self._config.get("custom_name", None)
                allowed_units: list[str] = self._config.get("units", [])
                for unit_name in allowed_units:
                    if unit_name not in self._units.keys():
                        unit = self.createUnit(unit_name)
                        if unit is not None:
                            self._units[unit_name] = unit
            for name, unit in self._units.items():
                self._logger.debug(f"Register Unit: {name} ...")
                unit.register(self._pluginManager)

        def stop(self):
            if self._glib_thr is not None:
                Mods.linux.dbus_common.deinit_dbus(logger=self._logger)
                self._glib_thread = None
        
        def sendStates(self):
            for unit in self._units.values():
                unit.resend()



except ImportError as ie:
    pass

class systemdConfig:
    def __init__(self):
        pass

    def configure(self, conff: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        con = conf.PluginConfig(conff, PluginLoader.getConfigKey())
        if con.get("units", None) is None:
            con["units"] = []
        while True:
            action = ConsoleInputTools.get_number_input("Was möchtest du tun? 0. Nichts 1. Unit hinzufügen 2. Unit löschen", 0)
            if action == 1:
                con["units"].append(ConsoleInputTools.get_input("Unit name?: "))
            elif action == 2:
                print("  0: Nichts löschen\n")
                for i in range(0, len(con["units"])):
                    print(f"  {i+1}: {con['units'][i]}\n")
                rem: int = ConsoleInputTools.get_number_input("Was soll entfernt werden?", 0)
                if rem == 0:
                    continue
                units: list[str] = con["units"]
                del units[rem-1]
            else:
                break

