# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as ad
from Tools.Devices.Sensor import Sensor, SensorDeviceClasses
from Tools.Devices.Filters import DeltaFilter, TooHighFilter, MinTimeElapsed
from Tools.PluginManager import PluginManager

import logging
import os
import re
import schedule

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "rpiCPUtemp"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return RaspberryPiCpuTemp(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        RaspberryPiCpuTempConfig(conf).run()


class RaspberryPiCpuTemp:
    _shed_Job = None
    _sensor: Sensor
    _plugin_manager: PluginManager

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._config = conf.PluginConfig(opts, "rpiCPUtemp")
        self.__client = client
        self.__logger = logger.getChild("PiCpuTemp")
        self._prev_deg = 0
        if self._config.get("diff", None) is None:
            self._config["diff"] = 1.5
        self._file = open("/sys/class/thermal/thermal_zone0/temp")
        self._callables = []

    def add_temperature_call(self, call):
        if callable(call):
            self._callables.append(call)

    def register(self):
        t = ad.Topics.get_std_devInf()
        n = self._config.get("name", "CPU Temp")
        self._shed_Job = schedule.every(
            self._config.get("update_secs", 15)
        ).seconds
        self._shed_Job.do(self.send_update)

        self._sensor = Sensor(
            self.__logger,
            self._plugin_manager,
            n,
            SensorDeviceClasses.TEMPERATURE,
            "C"
        )
        self._sensor.register()
        self._sensor.addFilter( MinTimeElapsed.MinTimeElapsedFilter(5.0) )
        self._sensor.addFilter( DeltaFilter.DeltaFilter(2.25) )
        self._sensor.addFilter( TooHighFilter.TooHighFilter(150.0) )


    def set_pluginManager(self, pm):
        self._plugin_manager = pm

    def stop(self):
        schedule.cancel_job(self._shed_Job)
        self._file.close()

    def sendStates(self):
        self.send_update(True)

    @staticmethod
    def get_temperatur_file(f):
        data = f.read()
        f.seek(0)
        return round(int(data) / 1000, 1)

    @staticmethod
    def get_temperatur(p) -> float:
        if os.path.isfile(p):
            data = None
            with open(p) as f:
                data = f.read()
                f.close()
            if data is not None:
                return round(int(data) / 1000, 2)
        return -1000

    def send_update(self, force=False):
        new_temp = self.get_temperatur_file(self._file)

        for call in self._callables:
            try:
                call(new_temp)
            except:
                self.__logger.exception("Temperature callback error")

        self._sensor(new_temp)


class RaspberryPiCpuTempConfig:
    def __init__(self, conf: conf.BasicConfig):
        self.c = conf

    def run(self):
        from Tools import ConsoleInputTools as cit
        self.c["rpiCPUtemp/name"] = cit.get_input("Unter welchem Namen soll die CPU Temperatur angegeben werden. \n-> ", require_val=True, std_val="CPU Temperatur")
        self.c["rpiCPUtemp/diff"] = cit.get_number_input("Wie viel muss sich die Temperatur ändern, um neue Temperatur zu senden= ", 0.5)
