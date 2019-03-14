# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import os
import re
import threading

import schedule

import smbus
import Mods.referenz.bh1750 as bhref

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "BHL1750"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return bhl1750(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        bhl1750Conf(conf).run()


class bhl1750:
    topic = None
    topic_alt = None

    _device_offline = True
    _devAlt_offline = True

    _dev_last = 0
    _dev_alt_last = 0

    _threasholds = [0,0]

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._client = client
        self._conf = opts
        self._logger = logger.getChild("BHL1750")
        self._devID = device_id
        
        self._job_inst = []
        self._bus = smbus.SMBus(self._conf["BHL1750/bus"])

    def register(self):
        if self._conf["BHL1750/device"]:
            self._logger.info("Erzeuge Autodiscovery Config für Addresse 1")
            unique_id = "sensor.bht1750-{}.{}".format(self._devID, "addr")
            self.topic = self._conf.get_autodiscovery_topic(conf.autodisc.Component.SENSOR, "Licht", conf.autodisc.SensorDeviceClasses.ILLUMINANCE)
            payload = self.topic.get_config_payload("Licht", "Lux", unique_id=unique_id)
            if (self.topic.config is not None):
                self._client.publish(self.topic.config, payload=payload, qos=0, retain=True)

        if self._conf["BHL1750/device_alt"]:
            self._logger.info("Erzeuge Autodiscovery Config für Addresse 2")
            unique_id = "sensor.bht1750-{}.{}".format(self._devID, "addr_alt")
            self.topic_alt = self._conf.get_autodiscovery_topic(conf.autodisc.Component.SENSOR, "Licht a", conf.autodisc.SensorDeviceClasses.ILLUMINANCE)
            payload = self.topic_alt.get_config_payload("Licht", "Lux", unique_id=unique_id)
            if (self.topic_alt.config is not None):
                self._client.publish(self.topic_alt.config, payload=payload, qos=0, retain=True)

        self._job_inst.append(schedule.every().seconds.do(bhl1750.send_update, self))
        self._job_inst.append(schedule.every(5).minute.do(bhl1750.update_threshhold, self))
        self.update_threshhold()

    def stop(self):
        for job in self._job_inst:
            schedule.cancel_job(job)
        self._client.publish(self.topic.ava_topic, "offline", retain=True)

    def update_threshhold(self):
        if self._conf["BHL1750/device"]:
            if self._dev_last > 900:
                self._threasholds[0] = 110
            elif self._dev_last > 500:
                self._threasholds[0] = 35
            elif self._dev_last > 250:
                self._threasholds[0] = 10
            else:
                self._threasholds[0] = 0.5

        if self._conf["BHL1750/device_alt"]:
            if self._dev_alt_last > 900:
                self._threasholds[1] = 110
            elif self._dev_alt_last > 500:
                self._threasholds[1] = 35
            elif self._dev_alt_last > 250:
                self._threasholds[1] = 10
            else:
                self._threasholds[1] = 0.5


    def send_update(self):
        if self.topic is not None:
            try:
                lux = bhref.convertToNumber( self._bus.read_i2c_block_data(bhref.DEVICE, bhref.CONTINUOUS_HIGH_RES_MODE_2) )
                lux = round(lux, 1)
                if bhl1750.inbetween(lux, self._dev_alt_last, self._threasholds[0]):
                    self._dev_last = lux
                    self._client.publish(self.topic.state, lux)
                    if self._device_offline:
                        self._client.publish(self.topic.ava_topic, "online", retain=True)
                        self._device_offline = False
            except OSError:
                self._client.publish(self.topic.ava_topic, "offline", retain=True)
                self._device_offline = True

        if self.topic_alt is not None:
            try:
                lux = bhref.convertToNumber( self._bus.read_i2c_block_data(bhref.DEVICE_ALT, bhref.CONTINUOUS_HIGH_RES_MODE_2) )
                lux = round(lux, 1)
                if bhl1750.inbetween(lux, self._dev_alt_last, self._threasholds[1]):
                    self._dev_alt_last = lux
                    self._client.publish(self.topic_alt.state, lux)
                    if (self._devAlt_offline):
                        self._client.publish(self.topic_alt.ava_topic, "online", retain=True)
                        self._devAlt_offline = False
            except OSError:
                self._client.publish(self.topic.ava_topic, "offline", retain=True)
                self._devAlt_offline = True

    @staticmethod
    def inbetween(toTest, oldVal, upDown):
        min = oldVal - upDown
        max = oldVal + upDown
        return toTest < min or toTest > max


class bhl1750Conf:
    def __init__(self, conf: conf.BasicConfig):
        self.c = conf
        self.c["BHL1750/device"] = False
        self.c["BHL1750/device_alt"] = False
        self.c["BHL1750/bus"] = -1

    def run(self):
        from Tools import ConsoleInputTools
        print(" Bekannte Busnummern: Bei Raspberry Rev1 = 0, Rev2 = 1 ")
        bus_nr = ConsoleInputTools.get_number_input("smbus nummer", 1)
        bus = smbus.SMBus(bus_nr)
        self.c["BHL1750/bus"] = bus_nr
        try:
            measument = bhref.convertToNumber(bus.read_i2c_block_data(bhref.DEVICE, bhref.ONE_TIME_HIGH_RES_MODE_1))
            self.c["BHL1750/device"] = ConsoleInputTools.get_bool_input("Auf Adresse wurden {} Lux gemessen. Verwenden?".format(measument))
        except OSError:
            pass
        try:
            measument = bhref.convertToNumber(bus.read_i2c_block_data(bhref.DEVICE_ALT, bhref.ONE_TIME_HIGH_RES_MODE_1))
            self.c["BHL1750/device_alt"] = ConsoleInputTools.get_bool_input("Auf Adresse_ALT wurden {} Lux gemessen. Verwenden?".format(measument))
        except OSError:
            pass   
