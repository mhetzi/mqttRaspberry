# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as ad
import logging
import os
import re
import schedule
import weakref

DEPENDENCIES_LOADED=True

try:
    from rpi_ws281x import PixelStrip, Color
except ImportError as ie:
    DEPENDENCIES_LOADED=False

from Tools.Devices import BinarySensor
from Tools import PluginManager

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "pWs2812B on RaspberryPi"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        try:
            from rpi_ws281x import PixelStrip, Color
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('rpi_ws281x', throw=ie, ask=False)
        return RaspberryPiWs281x(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        RaspberryPiWs281xConfig(conf).run()

    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            from rpi_ws281x import PixelStrip, Color
        except ImportError as ie:
            return ["rpi_ws281x"]
        return []

if DEPENDENCIES_LOADED:

    class RaspberryPiWs281x:
        _topic = None
        _shed_Job = None
        _plugin_manager = None

        def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
            self._config = conf.PluginConfig(opts, PluginLoader.getConfigKey())
            self.__client = client
            self.__logger = logger.getChild(PluginLoader.getConfigKey())
            self._prev_deg = True
            self.__lastTemp = 0.0
            self.__ava_topic = device_id
            self._callables = []
            self.device = None

        def set_pluginManager(self, pm):
            self._plugin_manager = weakref.ref(pm)

        def register(self):
            t = ad.Topics.get_std_devInf()
            self.device = BinarySensor.BinarySensor(
                self.__logger,
                self._plugin_manager(),
                self._config.get("name", "Undervoltage"),
                BinarySensor.autodisc.BinarySensorDeviceClasses.PROBLEM,
                ""
                )
            self.device.register()

        def stop(self):
            #schedule.cancel_job(self._shed_Job)
            pass

        def sendStates(self):
            self.send_update(True)

        def send_update(self, force=False):
            pass


class RaspberryPiWs281xConfig:
    def __init__(self, conff: conf.BasicConfig):
        self.c = conf.PluginConfig(conff, PluginLoader.getConfigKey())

    def run(self):
        from Tools import ConsoleInputTools as cit
        self.c["name"] = cit.get_input("Unter welchem Namen soll der LED Streifen angegeben werden. \n-> ", require_val=True, std_val="WS2812B")
        self.c[""] = cit.get_number_input("Wie oft soll getestet werden (Sekunen)?= ", 1)
