# -*- coding: utf-8 -*-

import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
from Tools.PluginManager import PluginLoader as pl

class PluginLoader(pl):

    @staticmethod
    def getConfigKey():
        return "Weatherflow"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger):
        import Mods.Weatherflow.plugin as p
        return p.WeatherflowPlugin( opts, logger)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        import Mods.Weatherflow.configurator as s
        s.WeatherflowConfigurator().configure(conf)

    @staticmethod
    def getNeededPipModules() -> list[str]:
        return []