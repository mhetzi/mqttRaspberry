# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as ad
import logging
import os
import re
import schedule
import weakref

DEPENDENCIES_LOADED=True

try:
    from rpi_bad_power import new_under_voltage
except ImportError as ie:
    DEPENDENCIES_LOADED=False

from Tools.Devices import BinarySensor
from Tools import PluginManager

class PluginLoader(PluginManager.PluginLoader):
    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            from rpi_bad_power import new_under_voltage
        except ImportError as ie:
            return ["rpi-bad-power"]
        return []

    @staticmethod
    def getConfigKey():
        return "rPiUndervoltage"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        try:
            from rpi_bad_power import new_under_voltage
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('rpi-bad-power', throw=ie, ask=False)
        return RaspberryPiUndervoltageDetector(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        RaspberryPiUndervoltageConfig(conf).run()

if DEPENDENCIES_LOADED:

    class RaspberryPiUndervoltageDetector:
        _topic = None
        _shed_Job = None
        _plugin_manager = None

        def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
            self._config = conf.PluginConfig(opts, PluginLoader.getConfigKey())
            self.__client = client
            self.__logger = logger.getChild(PluginLoader.getConfigKey())
            self._prev_deg = True
            self.__lastTemp = 0.0
            self.__ava_topic = device_id
            self._callables = []
            self.device = None

        def add_undervoltage_call(self, call):
            if callable(call):
                self._callables.append(call)

        def set_pluginManager(self, pm):
            self._plugin_manager = weakref.ref(pm)

        def register(self):
            t = ad.Topics.get_std_devInf()
            self.device = BinarySensor.BinarySensor(
                self.__logger,
                self._plugin_manager(),
                self._config.get("name", "Undervoltage"),
                BinarySensor.autodisc.BinarySensorDeviceClasses.PROBLEM,
                ""
                )
            self.device.register()
            self._shed_Job = schedule.every( self._config.get("checks", 1) ).seconds
            self._shed_Job.do(self.send_update)

        def stop(self):
            schedule.cancel_job(self._shed_Job)

        def sendStates(self):
            self.send_update(True)

        def send_update(self, force=False):
            undervoltage = new_under_voltage()

            if undervoltage is None:
                self.__logger.error("Undervoltage auf diesem System nicht unterstützt!")
            elif undervoltage.get() == self._prev_deg and not force:
                self.__logger.debug("Not changed {} last {} return".format(undervoltage.get(), self._prev_deg))
                return

            for call in self._callables:
                try:
                    call(undervoltage)
                except:
                    self.__logger.exception("Undervoltage callback error")
            self.__logger.debug("Publishing undervoltage {}.".format(undervoltage.get()))
            self._prev_deg = None if undervoltage is None else undervoltage.get()


class RaspberryPiUndervoltageConfig:
    def __init__(self, conf: conf.BasicConfig):
        self.c = conf

    def run(self):
        from Tools import ConsoleInputTools as cit
        self.c["rPiUndervoltage/name"] = cit.get_input("Unter welchem Namen soll die Strom unterfversorgung angegeben werden. \n-> ", require_val=True, std_val="Undervoltage")
        self.c["rPiUndervoltage/checks"] = cit.get_number_input("Wie oft soll getestet werden (Sekunen)?= ", 1)
