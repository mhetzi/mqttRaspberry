# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import os
import re
import schedule
import json

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


class OneWireTemp:

    def _reset_daily(self):
        for d in self._paths:
            i = d["i"]
            
            path_min = "w1t/stat/{}/min".format(i)
            path_max = "w1t/stat/{}/max".format(i)
            path_lmin = "w1t/stat/{}/lmin".format(i)
            path_lmax = "w1t/stat/{}/lmax".format(i)

            if self._config[path_min] == "RESET":
                continue
            elif self._config[path_max] == "RESET":
                continue

            current_min = self._config.get(path_min, "n/A")
            current_max = self._config.get(path_max, "n/A")

            self.__logger.debug("{} = {}".format(path_lmin, current_min))
            self._config.sett(path_lmin, current_min)
            self.__logger.debug("{} = {}".format(path_lmax, current_max))
            self._config.sett(path_lmax, current_max)

            self.__logger.debug("reset daily stats")
            self._config[path_min] = "RESET"
            self._config[path_max] = "RESET"

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._config = opts
        self.__client = client
        self.__logger = logger.getChild("w1Temp")
        self._paths = []
        self._prev_deg = []

        if isinstance(self._config.get("w1t", None), list):
            devices = self._config["w1t"]
            self._config["w1t"] = {}
            self._config["w1t/dev"] = devices

        for temp in self._config.get("w1t/dev", []):
            d = {
                "i": temp.get("id", ""),
                "n": temp.get("name", ""),
                "p": os.path.join("/sys/bus/w1/devices", temp.get("id", ""), "w1_slave")
            }
            self._paths.append(d)
            self.__logger.info("Temperaturfühler {} mit der ID {} wird veröffentlicht.".format(d["n"], d["i"]))
            self.__logger.info("Der Pfad ist \"{}\"".format(d["p"]))
            self._prev_deg.append(-1)
        self.__lastTemp = 0.0
        self.__ava_topic = device_id

    def register(self):
        for d in self._paths:
            unique_id = "sensor.w1-{}.{}".format(d["i"], d["n"])
            topics = self._config.get_autodiscovery_topic(conf.autodisc.Component.SENSOR, d["n"], conf.autodisc.SensorDeviceClasses.TEMPERATURE)
            if topics.config is not None:
                self.__logger.info("Werde AutodiscoveryTopic senden mit der Payload: {}".format(topics.get_config_payload(d["n"], "°C", unique_id=unique_id, value_template="{{ value_json.now }}", json_attributes=True)))
                self.__client.publish(
                    topics.config,
                    topics.get_config_payload(d["n"], "°C", unique_id=unique_id, value_template="{{ value_json.now }}", json_attributes=True),
                    retain=True
                )
            self.__client.will_set(topics.ava_topic, "offline", retain=True)
            self.__client.publish(topics.ava_topic, "online", retain=True)

        self._daily_job = schedule.every().day.at("00:00")
        self._daily_job.do( lambda: self._reset_daily() )

        self._job = schedule.every(60).seconds
        self._job.do( lambda: self.send_update() )
        self.send_update()


    def stop(self):
        schedule.cancel_job(self._daily_job)
        schedule.cancel_job(self._job)

    def sendStates(self):
        self.send_update(True)

    @staticmethod
    def get_temperature_from_id(id: str) -> float:
        p = os.path.join("/sys/bus/w1/devices", id)
        return OneWireTemp.get_temperatur(p)

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
                    return round(int(tmp) / 1000, 1)
        return -1000

    def send_update(self, force=False):
        for i in range(0, len(self._paths)):
            d = self._paths[i]
            new_temp = self.get_temperatur(d["p"])
            topics = self._config.get_autodiscovery_topic(conf.autodisc.Component.SENSOR, d["n"], conf.autodisc.SensorDeviceClasses.TEMPERATURE)

            if new_temp != self._prev_deg[i] or force:

                ii = d["i"]

                path_min = "w1t/stat/{}/min".format(ii)
                path_max = "w1t/stat/{}/max".format(ii)
                path_lmin = "w1t/stat/{}/lmin".format(ii)
                path_lmax = "w1t/stat/{}/lmax".format(ii)

                cmin = self._config.get(path_min, "RESET")
                cmax = self._config.get(path_max, "RESET")

                if cmin == "RESET" or cmin == "n/A":
                    cmin = new_temp
                elif cmin > new_temp:
                    cmin = new_temp
                if cmax == "RESET" or cmax == "n/A":
                    cmax = new_temp
                elif cmax < new_temp:
                    cmax = new_temp

                self._config[path_min] = cmin
                self._config[path_max] = cmax

                if self._config.get("w1t/diff/{}".format(ii), None) is not None:
                    diff = self._config["w1t/diff/{}".format(ii)]
                    if not (new_temp > (self._prev_deg[i] + diff)) and not (new_temp < (self._prev_deg[i] - diff)):
                        self.__logger.debug("Neue Temperatur {} hat sich nicht über {} verändert.".format(new_temp, diff))
                        return

                js = {
                    "now": str(new_temp),
                    "Heute höchster Wert": cmax,
                    "Heute tiefster Wert": cmin,
                    "Gestern höchster Wert": self._config.get(path_lmax, "n/A"),
                    "Gestern tiefster Wert": self._config.get(path_lmin, "n/A")
                }
                jstr = json.dumps(js)
                if new_temp != -1000 and self._prev_deg == -1000:
                    self.__client.publish(topics.ava_topic, "online", retain=True)
                    self.__client.publish(topics.state, jstr)
                elif new_temp != -1000:
                    self.__client.publish(topics.state, jstr)
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
        from Tools import ConsoleInputTools
        ids = self.get_available_ids()
        if len(ids) == 0:
            print(" === Keine Temperatur Sensoren gefunden. ===\n")
            self.c["w1t"] = None
            return
        for i in ids:
            r = input("Welchen Namen soll {} mit {}°C haben? ".format(i[0], OneWireTemp.get_temperatur(i[1])))
            self.c.get("w1t/dev", []).append({
                "id": i[0],
                "name": r
            })
            self.c["w1t/diff/{}".format(i[0])] = ConsoleInputTools.get_number_input("Wie viel Temperatur unterschied muss sein um zu senden? ", map_no_input_to=None)
        print("=== Alle Temperatur Sensoren benannt. ===\n")
