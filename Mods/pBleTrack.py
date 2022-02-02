# -*- coding: utf-8 -*-
# Um das skript ohne sudo verwenden zu können:
# sudo sudo setcap 'cap_net_raw,cap_net_admin+eip' $(readlink -f $(which python3))

import time
import datetime
try:
    from beacontools import BeaconScanner, EddystoneTLMFrame, EddystoneFilter
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('beacontools', throw=ie, ask=True)
    except err.RestartError:
        import beacontools
import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import Tools.PluginManager as pm

import threading
import json


class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "BleTrack"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        plugin = BleTrack(client, opts, logger, device_id)
        return plugin

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger: logging.Logger):
        from Tools import ConsoleInputTools
        conf["BleTrack/mode"] = ConsoleInputTools.get_bool_input(
            "Hauptsucher (nur einer pro MQTT instanz) ")
        conf["BleTrack/room"] = ConsoleInputTools.get_input("Name des Raums ")


class BleTag:
    def __init__(self):
        self.voltage = 0
        self.temperature = 32.799  # frame durch 1000
        self.advCount = 0
        self.uptime_sec = 0
        self.namespace = ""
        self.instance = ""
        self.room = "Garage"
        self.rssi = -200
        self._topic = None
        self._lastSeen = datetime.datetime.now()

    @staticmethod
    def fromString(data: str):
        tag = BleTag()
        d = json.loads(data)
        tag.voltage = d.get("mV", None)
        tag.temperature = d.get("°C")
        tag.advCount = d.get("c")
        tag.uptime_sec = d.get("up")
        tag.namespace = d.get("ns")
        tag.instance = d.get("i")
        tag.room = d.get("r")
        tag.rssi = d.get("s")
        return tag

    def toDict(self) -> dict:
        js = {
            "mV": self.voltage, "°C": self.temperature, "c": self.advCount, "up": self.uptime_sec,
            "ns": self.namespace, "i": self.instance, "r": self.room, "s": self.rssi
        }
        return js

    def toString(self) -> str:
        return json.dumps(self.toDict())


class BleTrack(threading.Thread):
    _pluginManager = None

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        threading.Thread.__init__(self)
        self.name = "BleTracker"
        self.__client = client
        self.__logger = logger.getChild("BleTrack")
        self._config = opts
        self._device_id = device_id
        self.__logger.debug("BleTrack.__init__()")

    def build_tag_sensor(self, tag: BleTag):
        sensorName = "BLEB{}-{}".format(tag.namespace, tag.instance)
        uid_tag = "sensor.ble-{}-{}".format(self._device_id, sensorName)
        tag._topic = self._config.get_autodiscovery_topic(
            conf.autodisc.Component.BINARY_SENROR,
            sensorName,
            conf.autodisc.BinarySensorDeviceClasses.MOTION
        )
        tag_payload = tag._topic.get_config_payload(
            sensorName, "", unique_id=uid_tag, value_template="{{ value_json.r }}", json_attributes=True)
        if tag._topic.config is not None:
            self.__client.publish(
                tag._topic.config, payload=tag_payload, qos=0, retain=True)

    def register(self):
        pass

    def set_pluginManager(self, p: pm.PluginManager):
        self._pluginManager = p

    def stop(self):
        pass

    def run(self):
        pass

    def sendStates(self):
        pass


if __name__ == "__main__":

    def callback(bt_addr, rssi, packet, additional_info):
        print("<%s, %d> %s %s" % (bt_addr, rssi, packet, additional_info))

    # scan for all TLM frames of beacons in the namespace "12345678901234678901"
    scanner = BeaconScanner(callback)
    scanner.start()

    time.sleep(10)
    scanner.stop()
