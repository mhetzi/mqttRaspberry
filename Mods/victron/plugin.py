# -*- coding: utf-8 -*-

import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as ad
import logging
import os
import re
import schedule
import weakref
try:
    import serial
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('pyserial', throw=ie, ask=True)
    except err.RestartError:
        import serial

import Mods.victron.Constants as CONST
from Mods.victron.vcSerial import Connection

from Mods.victron.mppt import MPPT

class VeDirectPlugin:
    _topic = None
    _shed_Job = None
    _plugin_manager = None
    _do_register = False
    _do_register_was_connected = False
    _veDevice: CONST.VEDirectDevice

    def _device_ready(self):
        self.__logger.debug("Gerät bereit.")
        self._subdevice = self._veDirCon._device
        self._subdevice_ready = True
        if self._do_register:
            self.__logger.debug("Gerät bereit. Do register_real()...")
            self.register_real(self._do_register_was_connected)

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._subdevice_ready = False
        self._config = conf.PluginConfig(opts, CONST.CONFIG_NAME)
        self.__client = client
        self.__logger = logger.getChild(CONST.CONFIG_NAME)
        self._prev_deg = None
        self.__lastTemp = 0.0
        self.__ava_topic = device_id
        self._veDevice = None

        self.__logger.debug("Erstelle verbindung...")
        self._veDirCon = Connection(self._config, self.__logger)
        self._veDirCon._device_ready_call = self._device_ready
        self._veDirCon.start()
        

    def set_pluginManager(self, pm):
        self._plugin_manager = pm

    def register(self, wasConnected):
        if self._subdevice_ready:
            return self.register_real(wasConnected)
        self._do_register_was_connected = wasConnected
        self._do_register = True

    def register_real(self, wasConnected):
        t = ad.Topics.get_std_devInf()
        self._veDirCon._device.via_device = t.IDs[0]
        self._do_register = False

        if not wasConnected:
            self._shed_Job = schedule.every( self._config.get("checks", 1) ).seconds
            self._shed_Job.do(self.send_update)

        if "MPPT" in self._veDirCon._device.model:
            self.__logger.info("MPPT gefunden!")
            self._veDevice = MPPT(self.__logger, self._plugin_manager, self._veDirCon)
            self._veDevice.register_entities()
        else:
            self.__logger.warning("Geräte PID {} nicht erkannt.".format(self._veDirCon._device.model))

    def stop(self):
        schedule.cancel_job(self._shed_Job)
        self._veDirCon.stop()

    def sendStates(self):
        self.send_update(True)

    def send_update(self, force=False):
        pass