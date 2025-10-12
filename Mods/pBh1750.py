# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import os
import re

import schedule
from Tools import PluginManager
import Tools.Config as tc

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "BH1750"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        try:
            import smbus
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('smbus', throw=ie, ask=False)
        return bh1750(opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        bh1750Conf(conf).run()
    
    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import smbus
        except ImportError as ie:
            return ["smbus"]
        return []


SKIP_CLASS_BUILDING = False

try:
    import smbus
except ImportError as ie:
    SKIP_CLASS_BUILDING = True

if not SKIP_CLASS_BUILDING:

    import Mods.referenz.bh1750 as bhref
    class bh1750(PluginManager.PluginInterface):
        topic = None
        topic_alt = None

        _device_offline = True
        _devAlt_offline = True

        _dev_last = 0
        _dev_alt_last = 0

        _threasholds = [0,0]
        __broken = False
        _devID = "unset_dev_id"

        def __init__(self, opts: conf.BasicConfig, logger: logging.Logger):
            self._logger = logger.getChild("BH1750")
            
            self._job_inst = []

            if opts.get("BHL1750", None) is not None:
                opts["BH1750"] = opts["BHL1750"]
                del opts["BHL1750"]

            self._conf = conf.PluginConfig(opts, "BH1750")

            try:
                self._bus = smbus.SMBus(self._conf["bus"])
            except:
                self._logger.exception("SMBus wurde nicht gefunden")
                self.__broken = True

        def register(self):
            if self.__broken:
                return
            self._devID = self._pluginManager._client_name
            if self._conf["device"]:
                self._logger.info("Erzeuge Autodiscovery Config für Addresse 1")
                unique_id = "sensor.bht1750-{}.{}".format(self._devID, "addr")
                self.topic = self._conf.get_autodiscovery_topic(conf.autodisc.Component.SENSOR, "Licht", conf.autodisc.SensorDeviceClasses.ILLUMINANCE)
                payload = self.topic.get_config_payload("Licht", "lux", unique_id=unique_id)
                if (self.topic.config is not None):
                    self._pluginManager._client.publish(self.topic.config, payload=payload, qos=0, retain=True)

            if self._conf["device_alt"]:
                self._logger.info("Erzeuge Autodiscovery Config für Addresse 2")
                unique_id = "sensor.bht1750-{}.{}".format(self._devID, "addr_alt")
                self.topic_alt = self._conf.get_autodiscovery_topic(conf.autodisc.Component.SENSOR, "Licht a", conf.autodisc.SensorDeviceClasses.ILLUMINANCE)
                payload = self.topic_alt.get_config_payload("Licht", "lux", unique_id=unique_id)
                if (self.topic_alt.config is not None):
                    self._pluginManager._client.publish(self.topic_alt.config, payload=payload, qos=0, retain=True)

            self._job_inst.append(schedule.every().second.do(bh1750.send_update, self))
            self._job_inst.append(schedule.every(5).minutes.do(bh1750.update_threshhold, self))

        def stop(self):
            for job in self._job_inst:
                schedule.cancel_job(job)
            self._pluginManager._client.publish(self.topic.ava_topic, "offline", retain=True)

        def update_threshhold(self):
            if self._conf["device"]:
                if self._dev_last > 900:
                    self._threasholds[0] = 325
                elif self._dev_last > 500:
                    self._threasholds[0] = 75
                elif self._dev_last > 250:
                    self._threasholds[0] = 30
                elif self._dev_last > 7:
                    self._threasholds[0] = 2
                elif self._dev_last > 3.5:
                    self._threasholds[0] = 1
                else:
                    self._threasholds[0] = 0.5
            if self._conf["device_alt"]:
                if self._dev_alt_last > 900:
                    self._threasholds[1] = 325
                elif self._dev_alt_last > 500:
                    self._threasholds[1] = 75
                elif self._dev_alt_last > 250:
                    self._threasholds[1] = 30
                elif self._dev_alt_last > 7:
                    self._threasholds[1] = 2
                elif self._dev_last > 3.5:
                    self._threasholds[1] = 1
                else:
                    self._threasholds[1] = 0.5
            self._logger.info("Threshold sind jetzt auf ({}, {})".format(self._threasholds[0], self._threasholds[1]))

        def sendStates(self):
            self._threasholds[1] = 0
            self._threasholds[0] = 0
            self.send_update()

        def send_update(self):
            if self.__broken:
                return
            if self.topic is not None:
                try:
                    lux = bhref.convertToNumber( self._bus.read_i2c_block_data(bhref.DEVICE, bhref.CONTINUOUS_HIGH_RES_MODE_2) )
                    lux = round(lux, 1)
                    if bh1750.inbetween(lux, self._dev_last, self._threasholds[0]):
                        self._dev_last = lux
                        self._pluginManager._client.publish(self.topic.state, lux)
                        if self._device_offline:
                            self._pluginManager._client.publish(self.topic.ava_topic, "online", retain=True)
                            self._device_offline = False
                            self.update_threshhold()
                except OSError:
                    self._pluginManager._client.publish(self.topic.ava_topic, "offline", retain=True)
                    self._device_offline = True
                    self._logger.exception("Kann kein update senden!")

            if self.topic_alt is not None:
                try:
                    lux = bhref.convertToNumber( self._bus.read_i2c_block_data(bhref.DEVICE_ALT, bhref.CONTINUOUS_HIGH_RES_MODE_2) )
                    lux = round(lux, 1)
                    if bh1750.inbetween(lux, self._dev_alt_last, self._threasholds[1]):
                        self._dev_alt_last = lux
                        self._pluginManager._client.publish(self.topic_alt.state, lux)
                        if (self._devAlt_offline):
                            self._pluginManager._client.publish(self.topic_alt.ava_topic, "online", retain=True)
                            self._devAlt_offline = False
                            self.update_threshhold()
                except OSError:
                    self._pluginManager._client.publish(self.topic.ava_topic, "offline", retain=True)
                    self._devAlt_offline = True

        def disconnected(self):
            return super().disconnected()

        @staticmethod
        def inbetween(toTest, oldVal, upDown):
            min = oldVal - upDown
            max = oldVal + upDown
            return toTest < min or toTest > max


class bh1750Conf:
    def __init__(self, conf: conf.BasicConfig):
        self.c = conf.PluginConfig(conf, "BH1750")
        self.c["device"] = False
        self.c["device_alt"] = False
        self.c["bus"] = -1

    def run(self):
        from Tools import ConsoleInputTools
        print(" Bekannte Busnummern: Bei Raspberry Rev1 = 0, Rev2 = 1 ")
        bus_nr = ConsoleInputTools.get_number_input("smbus nummer", 1)
        bus = smbus.SMBus(bus_nr)
        self.c["bus"] = bus_nr
        try:
            measument = bhref.convertToNumber(bus.read_i2c_block_data(bhref.DEVICE, bhref.ONE_TIME_HIGH_RES_MODE_1))
            self.c["device"] = ConsoleInputTools.get_bool_input("Auf Adresse wurden {} Lux gemessen. Verwenden?".format(measument))
        except OSError:
            pass
        try:
            measument = bhref.convertToNumber(bus.read_i2c_block_data(bhref.DEVICE_ALT, bhref.ONE_TIME_HIGH_RES_MODE_1))
            self.c["device_alt"] = ConsoleInputTools.get_bool_input("Auf Adresse_ALT wurden {} Lux gemessen. Verwenden?".format(measument))
        except OSError:
            pass   

class NewConfig(PluginManager.ConfiguratorInterface):

    @staticmethod
    def getConfigSchema() -> dict:
        m1 = ""
        return {
            "bus": PluginManager.SchemaEntry(str, "bus", "SMBus Nummer. (zb.: Raspberry Rev1 = 0, Rev2 = 1)", 1),
            "device": (bool, "device", "Sensor verwendet Primäre I²C Addresse", True),
            "device_alt": (bool, "device_alt", "Sensor verwendet Sekundäre I²C Addresse", False)
        }
        
    @staticmethod
    def getCurrentConfig(c: conf.BasicConfig) -> conf.PluginConfig:
        return conf.PluginConfig(c, "BH1750")