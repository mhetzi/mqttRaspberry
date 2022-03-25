from typing import Union
import paho.mqtt.client as mclient
import logging

import  Tools.Config as conf
from    Tools.PluginManager import PluginManager, PluginInterface
from    Tools.Devices.Sensor import Sensor, SensorDeviceClasses

from Mods.kaifa.kaifadevice import Reader


class KaifaPlugin(PluginInterface):
    __slots__ = ("_plugin_manager", "_devices", "_config", "__client", "__logger")

    _plugin_manager: Union[PluginManager, None]
    _devices: list[Reader]
    __logger: logging.Logger
    __client: mclient.Client
    _config: conf.PluginConfig

    def __init__(self, client: mclient.Client, opts: conf.PluginConfig, logger: logging.Logger, device_id: str):
        self._config = opts
        self.__client = client
        self.__logger = logger.getChild("kaifa")
        self._devices = []

        meters: list = self._config.get("meters", default=[])
        self.__logger.debug(f"Beginne mit verarbeiten von Meters: {meters = }")
        
        for dev in range( len(meters) ):
            meter_key = f"meters/{dev}"
            self.__logger.debug(f"Baue Reader({self._config = }, {meter_key = }, {self.__logger = })")
            self._devices.append( Reader(subConfig=conf.PluginConfig(self._config, meter_key), logger=self.__logger.getChild(str(dev))) )
        self.__logger.debug("Alle SmartMeter erstellt!")


    def set_pluginManager(self, pm: PluginManager):
        self._plugin_manager = pm
        for dev in self._devices:
            self.__logger.debug("Starte Serial Reader...")
            dev.start()

    def register(self, wasConnected=False):
        if self._plugin_manager is not None:
            for dev in self._devices:
                dev.register(self._plugin_manager)

    def stop(self):
        for dev in self._devices:
            dev.stop()

    def sendStates(self):
        self.send_update(True)

    def send_update(self, force=False):
        for dev in self._devices:
            dev.resend()