# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as ad
import logging
import os
import re
import schedule
import weakref

from Mods.victron.Constants import CONFIG_NAME
from Tools.PluginManager import PluginLoader as PLuginLoadeInterface

class PluginLoader(PLuginLoadeInterface):

    @staticmethod
    def getConfigKey():
        return CONFIG_NAME

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        try:
            from Mods.victron.plugin import VeDirectPlugin
            return VeDirectPlugin(opts, logger, device_id)
        except ModuleNotFoundError:
            logger.warning("Please update the git submodules.")
            return None
        

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        VeDirectConfig(conf).run()

    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import serial
        except ImportError as ie:
            return ["pyserial"]
        return []


class VeDirectConfig:
    def __init__(self, c: conf.BasicConfig):
        self.c = conf.PluginConfig(c, CONFIG_NAME)

    def run(self):
        from Tools import ConsoleInputTools
        from Mods.victron.plugin import VeDirectPlugin
        self.c["name"] = ConsoleInputTools.get_input("Gerätename überschreiben?. \n-> ", require_val=False, std_val=None)
