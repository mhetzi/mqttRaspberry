# -*- coding: utf-8 -*-
from typing import Union
from Tools import ConsoleInputTools
from Tools import PluginManager
from Tools.Config import PluginConfig

import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import os
import re
import schedule
import io
import json
import math

from Tools.Devices.Sensor import Sensor

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "udev_dbus"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        from Mods.udev.Main import UdevPlugin as pl
        return pl(PluginConfig(opts, PluginLoader.getConfigKey()), logger, device_id)

    @staticmethod
    def runConfig(bc: conf.BasicConfig, logger:logging.Logger):
        UdevPluginConfig(bc).run()
    
    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import pyudev
        except ImportError as ie:
            return ["pyudev"]
        return []


class UdevPluginConfig:
    def __init__(self, bc: conf.BasicConfig):
        self.__ids = []
        self.c = PluginConfig(bc, PluginLoader.getConfigKey())

    def run(self):
        self.c["displays/enabled"] = ConsoleInputTools.get_bool_input("Process Monitor States", False)

