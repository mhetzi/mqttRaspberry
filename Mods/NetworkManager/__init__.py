
from typing import IO, Union
from paho.mqtt.client import Client as MqttClient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import Tools.PluginManager as PluginMan
from Tools.Devices.Lock import Switch, Lock, LockState
from Tools.Devices.BinarySensor import BinarySensor
import logging
import schedule
import os

from time import sleep

#from Mods.linux.dbus_common import GlibThread, init_dbus

class PluginLoader(PluginMan.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "NetworkManager"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        try:
            import dasbus
            from main import NetworkManagerPlugin
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('dasbus', throw=ie, ask=False)
        return NetworkManagerPlugin(opts, logger.getChild(PluginLoader.getConfigKey()), device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        NmConfig().configure(conf, logger.getChild(PluginLoader.getConfigKey()))

    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import dasbus
        except ImportError as ie:
            return ["dasbus"]
        return []

class NmConfig:
    def __init__(self):
        pass

    def configure(self, conff: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        con = conf.PluginConfig(conff, PluginLoader.getConfigKey())
        con[PluginLoader.getConfigKey()] = "NOTHING"
