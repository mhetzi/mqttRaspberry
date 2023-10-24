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
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        import Mods.Weatherflow.plugin as p
        return p.WeatherflowPlugin(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        import Mods.Weatherflow.configurator as s
        s.WeatherflowConfigurator().configure(conf)

    @staticmethod
    def getNeededPipModules() -> list[str]:
        return []