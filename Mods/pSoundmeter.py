# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import os
import re
import schedule
import json
import threading

try:
    from soundmeter import meter
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('soundmeter', throw=ie, ask=True)
    except err.RestartError:
        from soundmeter import meter

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "soundmeter"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return SoundMeterWrapper(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        OneWireConf(conf).run()


class SoundMeterWrapper:

    def _reset_daily(self):
        pass

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._config = conf.PluginConfig(config=opts, plugin_name="soundmeter")
        self.__client = client
        self.__logger = logger.getChild("SoundMeter")
        self.__ava_topic = device_id
        self._topic = None
        self._wasTriggered = False
        self._lastRMS = -1000
        self._thread = None

    def register(self, was_connected):
        name = "Soundmeter"
        unique_id = "sensor.soundmeter-{}".format(self.__ava_topic)

        if self._config.get("minimum", None) is None:
            mv = "RMS"
            vt = "{{ value_json.rms }}"
            ty = conf.autodisc.Component.SENSOR
            ety = conf.autodisc.SensorDeviceClasses.GENERIC_SENSOR
        else:
            mv = ""
            vt = "{{ value_json.triggered }}"
            ty = conf.autodisc.Component.BINARY_SENROR
            ety = conf.autodisc.BinarySensorDeviceClasses.OCCUPANCY

        topics = self._config.get_autodiscovery_topic(ty, name, ety)
        if topics.config is not None:
            self.__logger.info("Werde AutodiscoveryTopic senden mit der Payload: {}".format(topics.get_config_payload(name, mv, unique_id=unique_id, value_template=vt, json_attributes=True)))
            self.__client.publish(
                topics.config,
                topics.get_config_payload(name, mv, unique_id=unique_id, value_template=vt, json_attributes=True),
                retain=True
            )
        self._topic = topics
        self.__client.will_set(topics.ava_topic, "offline", retain=True)
        self.__client.publish(topics.ava_topic, "online", retain=True)

        if not was_connected:
            self.meter = meter.Meter(
                collect=False,
                seconds=None,
                action=None,
                segment=self._config.get("segment",0.5)
            )
            self.meter.logging = self.__logger.getChild("Meter")
            self.meter.monitor = self.monitor
            self.meter.meter = lambda x: x

            self.__logger.info("Soundmeter mit {} Segment erstellt.".format(self._config.get("segment", 0.5)))

            self._thread = threading.Thread(name="Soundmonitor", target=self.thread_main)
            self._thread.start()

    def thread_main(self):
        while not self.meter._graceful:
            try:
                self.meter.start()
            except OSError:
                self.__logger.exception("Soundmonitor failed")
                import time
                time.sleep(60)
                pass
            except:
                break


    def monitor(self, rms):
        if rms == self._lastRMS:
            return
        self.__logger.debug("RMS: {}".format(rms) )
        threshold = self._config.get("minimum", None)
        if threshold is not None:
            if not self._wasTriggered and threshold <= rms:
                self.send_update(True, rms)
            elif self._wasTriggered and threshold > rms:
                self.send_update(False, rms)
        else:
            self.send_update(False, rms)
        self._lastRMS = rms

    def stop(self):
        self.meter.graceful()
        self.__logger.info("Warte auf soundmeter")
        self._thread.join()

    def sendStates(self):
        self.send_update(False, 0)

    def send_update(self, triggered, rms, force=False):
        js = {
            "rms": rms,
            "triggered": 1 if triggered else 0,
            "pRMS": self._lastRMS
        }
        self.__client.publish(self._topic.state, json.dumps(js))
        self._wasTriggered = triggered


class OneWireConf:
    def __init__(self, con: conf.BasicConfig):
        self.__ids = []
        self.c = conf.PluginConfig(config=con, plugin_name="soundmeter")

    def run(self):
        from Tools import ConsoleInputTools

        if ConsoleInputTools.get_bool_input("Als occupancy verwenden? ", True):
            self.c["minimum"] = ConsoleInputTools.get_number_input("Minimaler Wert für Bewegung ", 100)
        else:
            self.c["minimum"] = None
        
        self.c["segment"] = ConsoleInputTools.get_number_input("Wie viele Segmente für RMS verwenden? ", 0.5)

        print("=== Nichts mehr zu konfigurieren. ===\n")
