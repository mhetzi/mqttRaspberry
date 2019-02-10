# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import os
import re
import threading

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "w1t"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return OneWireTemp(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        OneWireConf(conf).run()


class OneWireTemp(threading.Thread):

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        threading.Thread.__init__(self)
        self._config = opts
        self.__client = client
        self.__logger = logger.getChild("w1Temp")
        self._paths = []
        self._prev_deg = []
        for temp in self._config.get("w1t", []):
            d = {
                "i": temp.get("id", ""),
                "n": temp.get("name", ""),
                "p": os.path.join("/sys/bus/w1/devices", temp.get("id", ""), "w1_slave")
            }
            self._paths.append(d)
            self.__logger.info("Temperaturfühler {} mit der ID {} wird veröffentlicht.".format(d["n"], d["i"]))
            self.__logger.info("Der Pfad ist \"{}\"".format(d["p"]))
            self._prev_deg.append(-1)
        self.__doStop = threading.Event()
        self.__lastTemp = 0.0
        self.__ava_topic = device_id
        self.setName("w1TempUpdater")
        self.start()

    def register(self):
        for d in self._paths:
            unique_id = "sensor.w1-{}.{}".format(d["i"], d["n"])
            topics = self._config.get_autodiscovery_topic(conf.autodisc.Component.SENSOR, d["n"], conf.autodisc.SensorDeviceClasses.TEMPERATURE)
            if topics.config is not None:
                self.__logger.info("Werde AutodiscoveryTopic senden mit der Payload: {}".format(topics.get_config_payload(d["n"], "°C", unique_id=unique_id)))
                self.__client.publish(topics.config, topics.get_config_payload(d["n"], "°C", unique_id=unique_id), retain=True)
            self.__client.will_set(topics.ava_topic, "offline", retain=True)
            self.__client.publish(topics.ava_topic, "online", retain=True)

    def stop(self):
        self.__doStop.set()
        self.join()

    def run(self):
        count = 0
        while not self.__doStop.wait(1.0):
            count += 1
            if count > 10:
                self.send_update()
                count = 0

    @staticmethod
    def get_temperatur(p) -> float:
        if os.path.isfile(p):
            data = None
            with open(p) as f:
                data = f.read()
            if data is not None:
                tmp = re.search("t=.*", data)
                if tmp is not None:
                    tmp = tmp.group(0).replace("t=", "")
                    return round(int(tmp) / 1000, 2)
        return -1000

    def send_update(self):
        for i in range(0, len(self._paths)):
            d = self._paths[i]
            new_temp = self.get_temperatur(d["p"])
            topics = self._config.get_autodiscovery_topic(conf.autodisc.Component.SENSOR, d["n"], conf.autodisc.SensorDeviceClasses.TEMPERATURE)

            if new_temp != self._prev_deg[i]:
                if new_temp != -1000 and self._prev_deg == -1000:
                    self.__client.publish(topics.ava_topic, "online", retain=True)
                    self.__client.publish(topics.state, str(new_temp))
                elif new_temp != -1000:
                    self.__client.publish(topics.state, str(new_temp))
                else:
                    self.__client.publish(topics.ava_topic, "offline", retain=True)
                self._prev_deg[i] = new_temp


class OneWireConf:
    def __init__(self, conf: conf.BasicConfig):
        self.__ids = []
        self.c = conf

    def get_available_ids(self):
        ids = []
        import glob
        g = glob.glob("/sys/bus/w1/devices/*/w1_slave")
        for p in g:
            tp = p.replace("/sys/bus/w1/devices/", "").replace("/w1_slave", "")
            ids.append( (tp, p) )
        return ids

    def run(self):
        ids = self.get_available_ids()
        if len(ids) == 0:
            print(" === Keine Temperatur Sensoren gefunden. ===\n")
            self.c["w1t"] = None
            return
        for i in ids:
            r = input("Welchen Namen soll {} mit {}°C haben? ".format(i[0], OneWireTemp.get_temperatur(i[1])))
            self.c.get("w1t", []).append({
                "id": i[0],
                "name": r
            })
        print("=== Alle Temperatur Sensoren benannt. ===\n")
