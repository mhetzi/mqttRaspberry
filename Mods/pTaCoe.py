# -*- coding: utf-8 -*-

import paho.mqtt.client as mclient
import Tools.Config as conf
import logging

from Mods.CoE import getConfigKey


class PluginLoader:

    @staticmethod
    def getConfigKey():
        return getConfigKey()

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        from Mods.CoE.plugin import TaCoePlugin
        return TaCoePlugin(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        from Mods.CoE.configurator import CoEConfigurator
        CoEConfigurator().configure(conf)

