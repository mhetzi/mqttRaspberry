# -*- coding: utf-8 -*-

import paho.mqtt.client as mclient
import Tools.Config as conf
import logging

from Mods.CoE import getConfigKey
from Tools import PluginManager

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return getConfigKey()

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        from Mods.CoE.plugin import TaCoePlugin
        return TaCoePlugin(opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        from Mods.CoE.configurator import CoEConfigurator
        CoEConfigurator().configure(conf)
    
    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import bitstring
        except ImportError as ie:
            return ["bitstring"]
        return []

