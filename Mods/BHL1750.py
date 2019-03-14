# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import os
import re
import threading

import schedule

import smbus
import referenz.bh1750 as bhref

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
    topic: conf.autodisc.Topics = None
    topic_alt: conf.autodisc.Topics = None

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._client = client
        self._conf = opts
        self._logger = logger.getChild("BHL1750")
        self._devID = device_id
        
        self._job_inst = None
        self._bus = smbus.SMBus(self._conf["BHL1750/bus"])

    def register(self):
        if self._conf["BHL1750/device"]:
            self._logger.info("Erzeuge Autodiscovery Config für Addresse 1")
            unique_id = "sensor.bht1750-{}.{}".format(self._devID, "addr")
            self.topic = self._conf.get_autodiscovery_topic(conf.autodisc.Component.SENSOR, "Licht", conf.autodisc.SensorDeviceClasses.ILLUMINANCE)
            payload = self.topic.get_config_payload("Licht", "Lux", unique_id=unique_id)
            if (self.topic.config is not None):
                self._client.publish(self.topic.config, payload=payload, qos=0, retain=True)
            self._client.publish(self.topic.ava_topic, "online", retain=True)

        if self._conf["BHL1750/device_alt"]:
            self._logger.info("Erzeuge Autodiscovery Config für Addresse 2")
            unique_id = "sensor.bht1750-{}.{}".format(self._devID, "addr_alt")
            self.topic_alt = self._conf.get_autodiscovery_topic(conf.autodisc.Component.SENSOR, "Licht a", conf.autodisc.SensorDeviceClasses.ILLUMINANCE)
            payload = self.topic_alt.get_config_payload("Licht", "Lux", unique_id=unique_id)
            if (self.topic_alt.config is not None):
                self._client.publish(self.topic_alt.config, payload=payload, qos=0, retain=True)
            self._client.publish(self.topic_alt.ava_topic, "online", retain=True)

        self._job_inst = schedule.every().seconds.do(bhl1750.send_update, self)

    def stop(self):
        schedule.cancel_job(self._job_inst)
        self._client.publish(self.topic.ava_topic, "offline", retain=True)

    def send_update(self):
        if self.topic is not None:
            lux = bhref.convertToNumber( self._bus.read_i2c_block_data(bhref.DEVICE, bhref.ONE_TIME_HIGH_RES_MODE_1) )
            self._client.publish(self.topic.state, lux)
        if self.topic_alt is not None:
            lux = bhref.convertToNumber( self._bus.read_i2c_block_data(bhref.DEVICE_ALT, bhref.ONE_TIME_HIGH_RES_MODE_1) )
            self._client.publish(self.topic_alt.state, lux)

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

        measument = bus.read_i2c_block_data(bhref.DEVICE, bhref.ONE_TIME_HIGH_RES_MODE_1)
        self.c["BHL1750/device"] = ConsoleInputTools.get_bool_input("Auf Adresse wurden {} Lux gemessen. Verwenden?".format(bhref.convertToNumber(measument)))
        measument = bhref.convertToNumber(bus.read_i2c_block_data(bhref.DEVICE_ALT, bhref.ONE_TIME_HIGH_RES_MODE_1))
        self.c["BHL1750/device_alt"] = ConsoleInputTools.get_bool_input("Auf Adresse_ALT wurden {} Lux gemessen. Verwenden?".format(measument))