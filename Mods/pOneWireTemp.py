# -*- coding: utf-8 -*-
import pathlib
import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import os
import re
import schedule
import io
import json
import math

from Tools.Devices.Sensor import Sensor, SensorDeviceClasses
from Tools.Devices.Filters.DeltaFilter import DeltaFilter
from Tools.Devices.Filters.TooHighFilter import TooHighFilter

from Tools import PluginManager

class PluginLoader(PluginManager.PluginLoader):
    @staticmethod
    def getNeededPipModules() -> list[str]:
        return []

    @staticmethod
    def getConfigKey():
        return "w1t"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger):
        return OneWireTemp(opts, logger)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        OneWireConf(conf).run()


class OneWireTemp(PluginManager.PluginInterface):
    _plugin_manager: PluginManager.PluginManager | None = None
    _config: conf.PluginConfig

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

    def __init__(self, opts: conf.BasicConfig, logger: logging.Logger):
        self.__logger = logger.getChild("w1Temp")
        self._paths = []
        self._prev_deg = []
        
        if not isinstance(self._config.get("w1t", None), list):
            self.__logger.warning("w1t entry is not a list entry. Resetting...")
            devices = opts["w1t"]
            opts["w1t"] = {}
            opts["w1t/dev"] = devices
        self._config = conf.PluginConfig(opts, "w1t")
        self._build_paths()

    def _build_paths(self):
        self._prev_deg = []
        self._paths = []
        devices = self._config.get("w1t/dev", [])
        for temp in devices:
            path = pathlib.Path("/sys/bus/w1/devices").joinpath(temp.get("id", "")).joinpath("w1_slave")
            try:
                f = path.open("r")
            except FileNotFoundError:
                f = None
            d = {
                "i": temp.get("id", ""),
                "n": temp.get("name", ""),
                "p": path,
                "f": f
            }
            self._paths.append(d)
            self.__logger.info("Temperaturfühler {} mit der ID {} wird veröffentlicht.".format(d["n"], d["i"]))
            self.__logger.info("Der Pfad ist \"{}\"".format(d["p"]))
            self._prev_deg.append(math.nan)

    def set_pluginManager(self, pm):
        self._plugin_manager = pm

    def disconnected(self):
        return super().disconnected()

    def register(self):
        if self._plugin_manager is None:
            self._logger.error("PluginManager is none!")
            return
        self.__logger.debug("Sensoren für {} werden erstellt...".format(self._paths))
        for d in self._paths:
            unique_id = "sensor.w1-{}.{}".format(d["i"], d["n"])
            sensor = Sensor(self.__logger, self._plugin_manager, d["n"], SensorDeviceClasses.TEMPERATURE, "°C", unique_id=unique_id, value_template="{{ value_json.now }}", json_attributes=True, ownOfflineTopic=True)
            sensor.addFilter( TooHighFilter(500.0, self.__logger) )
            sensor.addFilter( DeltaFilter(self._config["w1t/diff/{}".format(d["i"])], self.__logger) )
            sensor.register()
            d["d"] = sensor

        self._daily_job = schedule.every().day.at("00:00")
        self._daily_job.do( lambda: self._reset_daily() )

        self._job = schedule.every(60).seconds
        self._job.do( lambda: self.send_update() )
        self.send_update()


    def stop(self):
        schedule.cancel_job(self._daily_job)
        schedule.cancel_job(self._job)
        for i in range(0, len(self._paths)):
            try:
                d = self._paths[i]
                d["f"].close()
            except:
                self.__logger.exception("Schlie0en der Datei fehlgeschlagen!")

    def sendStates(self):
        self.send_update(True)

    @staticmethod
    def get_temperature_from_id(id: str) -> float:
        p = os.path.join("/sys/bus/w1/devices", id)
        return OneWireTemp.get_temperatur(p)

    @staticmethod
    def get_temperatur_file(f):
        data = f.read()
        f.seek(0)
        tmp = re.search("t=.*", data)
        if tmp is not None:
            tmp = tmp.group(0).replace("t=", "")
            tmp = round(int(tmp) / 1000, 1)
            if tmp > 500.0:
                return math.nan
            elif tmp < -100.0:
                return math.nan
            return tmp
        return math.nan

    @staticmethod
    def get_temperatur(p) -> float:
        if os.path.isfile(p):
            with open(p) as f:
                return OneWireTemp.get_temperatur_file(f)
        return math.nan

    def send_update(self, force=False):
        try:
            self.__logger.debug("send_update for:")
            for i in range(0, len(self._paths)):
                d = self._paths[i]
                self.__logger.debug("Read Temperature for {}...".format(d))

                path: pathlib.Path = d["p"]

                try:
                    if d["f"] is None and path.exists():
                        self._build_paths()
                        self.register()
                        return
                    new_temp = self.get_temperatur_file(d["f"]) if d["f"] is not None else math.nan
                except ValueError:
                    d["f"] = None
                    return

                sensor: Sensor = d["d"]

                if new_temp != self._prev_deg[i] or force:

                    ii = d["i"]

                    path_min = "w1t/stat/{}/min".format(ii)
                    path_max = "w1t/stat/{}/max".format(ii)
                    path_lmin = "w1t/stat/{}/lmin".format(ii)
                    path_lmax = "w1t/stat/{}/lmax".format(ii)
                    path_sanity = "w1t/stat/{}/last".format(ii)

                    cmin = self._config.get(path_min, "RESET")
                    cmax = self._config.get(path_max, "RESET")
                    last = self._config.get(path_sanity, 0.1)
                    if last == 0.000:
                        last= 0.0001
                    self._config[path_sanity] = new_temp

                    percentage_cahnged = 100 / last * new_temp
                    if percentage_cahnged < 70 or percentage_cahnged > 140:
                        self.__logger.warning("Neue Temperatur hat zu hohe differenz: {}%".format(percentage_cahnged))
                        continue
                    
                    if not math.isnan(new_temp):
                        if cmin == "RESET" or cmin == "n/A" or math.isnan(cmin):
                            cmin = new_temp
                        elif cmin > new_temp and not math.isnan(new_temp):
                            cmin = new_temp
                        if cmax == "RESET" or cmax == "n/A" or math.isnan(cmax):
                            cmax = new_temp
                        elif cmax < new_temp and not math.isnan(new_temp):
                            cmax = new_temp

                        self._config[path_min] = cmin
                        self._config[path_max] = cmax

                    js = {
                            "now": new_temp,
                            "Heute höchster Wert": cmax,
                            "Heute tiefster Wert": cmin,
                            "Gestern höchster Wert": self._config.get(path_lmax, "n/A"),
                            "Gestern tiefster Wert": self._config.get(path_lmin, "n/A")
                        }

                    if math.isnan(new_temp):
                        self.__logger.info("OneWire device offline.")
                        sensor.offline()
                    else:
                        self.__logger.debug(f"Send State: {js}")
                        sensor.state(js, keypath="now")

                    self._prev_deg[i] = new_temp
        except:
            self.__logger.exception("send_update() failed.")
        self.__logger.debug(" endfor")


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
