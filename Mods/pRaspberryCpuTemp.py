# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as ad
import logging
import os
import re
import threading
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
    _topic = None
    _shed_Job = None

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        threading.Thread.__init__(self)
        self._config = opts
        self.__client = client
        self.__logger = logger.getChild("PiCpuTemp")
        self._prev_deg = 0
        self.__lastTemp = 0.0
        self.__ava_topic = device_id

    def register(self):
        t = ad.Topics.get_std_devInf()
        n = self._config.get("rpiCPUtemp/name", "CPU Temp")
        unique_id = "sensor.PiCpuTemp-{}.{}".format(t.pi_serial, n)
        topics = self._config.get_autodiscovery_topic(conf.autodisc.Component.SENSOR, n, conf.autodisc.SensorDeviceClasses.TEMPERATURE)
        if topics.config is not None:
            self.__logger.info("Werde AutodiscoveryTopic senden mit der Payload: {}".format(topics.get_config_payload(n, "°C", unique_id=unique_id)))
            self.__client.publish(topics.config, topics.get_config_payload(n, "°C", unique_id=unique_id), retain=True)
        self.__client.will_set(topics.ava_topic, "offline", retain=True)
        self.__client.publish(topics.ava_topic, "online", retain=True)
        self._topic = topics
        self._shed_Job = schedule.every(1).minutes
        self._shed_Job.do(self.send_update)

    def stop(self):
        schedule.cancel_job(self._shed_Job)

    def sendStates(self):
        self.send_update(True)

    @staticmethod
    def get_temperatur(p) -> float:
        if os.path.isfile(p):
            data = None
            with open(p) as f:
                data = f.read()
            if data is not None:
                return round(int(data) / 1000, 2)
        return -1000

    def send_update(self, force=False):
        new_temp = self.get_temperatur("/sys/class/thermal/thermal_zone0/temp")

        if new_temp != self._prev_deg or force:
            if new_temp != -1000 and self._prev_deg == -1000:
                self.__client.publish(self._topic.ava_topic, "online", retain=True)
                self.__client.publish(self._topic.state, str(new_temp))
            elif new_temp != -1000:
                self.__client.publish(self._topic.state, str(new_temp))
            else:
                self.__client.publish(self._topic.ava_topic, "offline", retain=True)
            self._prev_deg = new_temp


class RaspberryPiCpuTempConfig:
    def __init__(self, conf: conf.BasicConfig):
        self.c = conf

    def run(self):
        from Tools import ConsoleInputTools as cit
        self.c["rpiCPUtemp/name"] = cit.get_input("Unter welchem Namen soll die CPU Temperatur angegeben werden. \n-> ", require_val=True, std_val="CPU Temperatur")
