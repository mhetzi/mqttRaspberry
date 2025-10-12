# -*- coding: utf-8 -*-
from typing import Union
from Tools import PluginManager
import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as ad
import logging
import os
import re
import schedule
import weakref

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "MS_Windows_Sensors"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger):
        try:
            import wmi
        except ImportError as ie:
                import Tools.error as err
                err.try_install_package('wmi', throw=ie, ask=False)
        return MsWindowsMain(opts, logger)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        MsWindowsMainConfig(conf).run()
    
    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import wmi
        except ImportError as ie:
            return ["wmi"]
        return []


try:
    import wmi
    from Tools.Devices import BinarySensor

    from Mods.win32submods.wmi_PnP import WMI_PnP
    from Mods.win32submods.pwr.WindowEvents import WindowEventProcessor
    from Mods.win32submods.systray import win32Systray

    class MsWindowsMain:
        _topic = None
        _shed_Job = None
        _plugin_manager = None

        _wmi_devices: Union[WMI_PnP, None] = None

        def __init__(self, opts: conf.BasicConfig, logger: logging.Logger):
            self._config = conf.PluginConfig(opts, PluginLoader.getConfigKey())
            self.__logger = logger.getChild(PluginLoader.getConfigKey())
            self._prev_deg = True
            self.__lastTemp = 0.0
            self._callables = []
            self.device = None
            self._running_sensor = None

            if self._config.get("enabled/systray", True):
                self._systray = win32Systray(self._config, self.__logger)
            if self._config.get("enabled/powerevents", True):
                self._pwr_ev = WindowEventProcessor(self._config, self.__logger)
            if self._config.get("enabled/wmi_pnp", True):
                self._wmi_devices = WMI_PnP(self._config, self.__logger)

        def set_pluginManager(self, pm: PluginManager.PluginManager):
            self._plugin_manager = pm

        def register(self, wasConnected=False):
            if self._plugin_manager is None:
                raise Exception("PluginManager is None!")
            if self._wmi_devices is not None:
                self._wmi_devices.register(wasConnected, self._plugin_manager)
            if self._pwr_ev is not None:
                self._pwr_ev.register(wasConnected, self._plugin_manager)
            if self._systray is not None:
                self._systray.register(wasConnected, self._plugin_manager)
            self._running_sensor = BinarySensor.BinarySensor(self.__logger, self._plugin_manager, "Windows gestartet", BinarySensor.BinarySensorDeviceClasses.POWER)
            self._running_sensor.register()
            self._running_sensor.turnOn()

        def stop(self):
            #schedule.cancel_job(self._shed_Job)
            if self._running_sensor is not None:
                self._running_sensor.turnOff()
            try:
                if self._pwr_ev is not None:
                    self._pwr_ev.shutdown()
            except:
                self.__logger.exception("Stoppen von PWR events")
            try:
                if self._wmi_devices is not None:
                    self._wmi_devices.shutdown_watchers()
            except:
                self.__logger.exception("Stoppen von wmi")
            try:
                if self._systray is not None:
                    self._systray.shutdown()
            except:
                self.__logger.exception("Stoppen von Systray")

        def sendStates(self):
            self.send_update(True)

        def send_update(self, force=False):
            if self._wmi_devices is not None:
                self._wmi_devices.sendUpdate(force)
            if self._pwr_ev is not None:
                self._pwr_ev.sendUpdate(force)
            if self._systray is not None:
                self._systray.sendUpdate(force)

        def disconnected(self):
            if self._systray is not None:
                self._systray.disconnected()

except ImportError as ie:
    pass

class MsWindowsMainConfig:
    def __init__(self, conff: conf.BasicConfig):
        self.c = conf.PluginConfig(conff, PluginLoader.getConfigKey())

    def run(self):
        from Tools import ConsoleInputTools as cit
        self.c["name"] = cit.get_input("Unter welchem Namen soll der PC angegeben werden. \n-> ", require_val=True, std_val="WindowsPC")
        self.c["enabled/wmi_pnp"] = cit.get_bool_input("PnP Geräte aktivieren? \n->", True)
        self.c["enabled/powerevents"] = cit.get_bool_input("PowerEvents aktivieren? \n->", True)
        self.c["enabled/systray"] = cit.get_bool_input("Systemtray aktivieren? \n->", True)

        if self.c["enabled/systray"]:
            print("CTRL-C drücken sobald kein neuer Aktionseintrag erstellt werden soll.")
            while True:
                try:
                    name, entry = win32Systray.getNewDeviceEntry()
                    self.c["systray/itemList/{}".format(name)] = entry
                except KeyboardInterrupt:
                    break
