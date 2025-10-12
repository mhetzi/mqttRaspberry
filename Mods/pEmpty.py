
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

class PluginLoader(PluginMan.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "Empty"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger):
        try:
            import example
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('example', throw=ie, ask=False)
        return EmptyPlugin(opts, logger.getChild("Empty"))

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        EmptyConfig().configure(conf, logger.getChild(PluginLoader.getConfigKey()))

    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import example
        except ImportError as ie:
            return ["example"]
        return []


class EmptyPlugin(PluginMan.PluginInterface):
    def __init__(self, opts: conf.BasicConfig, logger: logging.Logger):
        pass
    
    def set_pluginManager(self, pm:PluginMan.PluginManager):
        pass

    def register(self, wasConnected=False):
        pass

    def stop(self):
        pass

    def sendStates(self):
        pass

class EmptyConfig:
    def __init__(self):
        pass

    def configure(self, conff: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        con = conf.PluginConfig(conff, "logind")
        con[PluginLoader.getConfigKey()] = "NOTHING"
