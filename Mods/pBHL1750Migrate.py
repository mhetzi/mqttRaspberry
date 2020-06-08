# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import os
import re

import schedule

try:
    import smbus
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('smbus', throw=ie, ask=True)
    except err.RestartError:
        import smbus
import Mods.referenz.bh1750 as bhref

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "BHL1750"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        from Mods.pBh1750 import bh1750
        return bh1750(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        from Mods.pBh1750 import bh1750Conf
        bh1750Conf(conf).run()