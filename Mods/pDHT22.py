# -*- coding: utf-8 -*-
import json
import logging
import os
import re
import math

import paho.mqtt.client as mclient
import schedule


from Tools import PluginManager 
import Tools.Config as conf

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "DHT"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        try:
            import Adafruit_DHT
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('Adafruit_DHT', throw=ie, ask=False)
        return DHT22(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        c = DhtConf(conf)
        c.run()

    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import Adafruit_DHT
        except ImportError as ie:
            return ["Adafruit_DHT"]
        return []

BUILD_CLASS = True


try:
    import Adafruit_DHT
except ImportError as ie:
    BUILD_CLASS = False
        
if BUILD_CLASS:

    from Tools import RangeTools

    from Tools.Devices.Sensor import Sensor, SensorDeviceClasses
    from Tools.Devices.Filters.TooHighFilter import TooHighFilter
    from Tools.Devices.Filters.RangedFilter import RangedFilter

    class DHT22(PluginManager.PluginInterface):
        _temp_topic = None
        _rh_topic = None
        _sensor_celsius: Sensor = None
        _sensor_humidity: Sensor = None

        def _reset_daily(self):
            for i in ["°c", "rH%"]:
                
                path_min  = "DHT/stat/{}/min".format(i)
                path_max  = "DHT/stat/{}/max".format(i)
                path_lmin = "DHT/stat/{}/lmin".format(i)
                path_lmax = "DHT/stat/{}/lmax".format(i)

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
            self._config   = opts
            self.__client  = client
            self.__logger  = logger.getChild("w1Temp")
            self._prev_deg = [None,None]
            self.dht = None
            self._plugin_manager = None

            if isinstance(self._config.get("DHT", None), list):
                devices = self._config["DHT"]
                self._config["DHT"] = {}
                self._config["DHT/dev"] = devices

            sensor_map = { '11': Adafruit_DHT.DHT11,
                    '22': Adafruit_DHT.DHT22,
                    '2302': Adafruit_DHT.AM2302 }

            self.dht = sensor_map.get(self._config.get("DHT/dev/type", "22"), Adafruit_DHT.DHT22)
            
            self.__lastTemp = 0.0
            self.__ava_topic = device_id

        def register(self):

            # Registriere Temperatur
            unique_id = "sensor.dht-{}.{}.c".format(
                self._config.get("DHT/dev/type", "22"),
                self._config.get("DHT/name", "DHT")
            )
            self._temp_topic = self._config.get_autodiscovery_topic(
                conf.autodisc.Component.SENSOR,
                "{}_C".format(self._config.get("DHT/name", "DHT")),
                conf.autodisc.SensorDeviceClasses.TEMPERATURE
            )

            self._sensor_celsius = Sensor(
                self.__logger.getChild("Celsuis"),
                self._plugin_manager,
                "{}_C".format(self._config.get("DHT/name", "DHT")),
                SensorDeviceClasses.TEMPERATURE, "°C", 
                unique_id=unique_id, value_template="{{ value_json.now }}", json_attributes=True
            )
            self._sensor_celsius.register()
            self._sensor_celsius.addFilter(TooHighFilter(40.0, self.__logger.getChild("Celsius")))
            self._sensor_celsius.addFilter(RangedFilter(5.0, 5, self.__logger.getChild("Celsius")))

            # Registriere Luftfeuchte
            unique_id = "sensor.dht-{}.{}.rh".format(
                self._config.get("DHT/dev/type", "22"),
                self._config.get("DHT/name", "DHT"),
            )
            self._sensor_humidity = Sensor(
                self.__logger.getChild("Humidity"),
                self._plugin_manager,
                "{}_Rh".format(self._config.get("DHT/name", "DHT")),
                SensorDeviceClasses.HUMIDITY, "%", 
                unique_id=unique_id, value_template="{{ value_json.now }}", json_attributes=True
            )
            self._sensor_humidity.register()
            self._sensor_humidity.addFilter(TooHighFilter(100.0, self.__logger.getChild("Humidity")))
            self._sensor_humidity.addFilter(RangedFilter(5.0, 5, self.__logger.getChild("Humidity")))

            self._daily_job = schedule.every().day.at("00:01")
            self._daily_job.do( lambda: self._reset_daily() )

            self._job = schedule.every(self._config.get("DHT/update_seconds", 60)).seconds
            self._job.do( lambda: self.send_update() )


        def stop(self):
            schedule.cancel_job(self._daily_job)
            schedule.cancel_job(self._job)

        def sendStates(self):
            self.send_update(True)

        def sendTemperature(self, degree, force):
            new_temp = degree

            if new_temp != self._prev_deg[0] or force:
                ii = "°c"

                path_min = "DHT/stat/{}/min".format(ii)
                path_max = "DHT/stat/{}/max".format(ii)
                path_lmin = "DHT/stat/{}/lmin".format(ii)
                path_lmax = "DHT/stat/{}/lmax".format(ii)

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

                js = {
                    "now": new_temp,
                    "Heute höchster Wert": cmax,
                    "Heute tiefster Wert": cmin,
                    "Gestern höchster Wert": self._config.get(path_lmax, "n/A"),
                    "Gestern tiefster Wert": self._config.get(path_lmin, "n/A")
                }
                if new_temp != -1000 and self._prev_deg == -1000:
                    self.__client.publish(self._temp_topic.ava_topic, "online", retain=True)
                    self._sensor_celsius(js, keypath="now")
                elif new_temp != -1000:
                    self._sensor_celsius(js, keypath="now")
                else:
                    self.__client.publish(self._temp_topic.ava_topic, "offline", retain=True)
                self._prev_deg[0] = new_temp

        def sendHumidity(self, rel_hum, force):
            new_temp = rel_hum

            if new_temp != self._prev_deg[1] or force:
                ii = "rH%"

                path_min = "DHT/stat/{}/min".format(ii)
                path_max = "DHT/stat/{}/max".format(ii)
                path_lmin = "DHT/stat/{}/lmin".format(ii)
                path_lmax = "DHT/stat/{}/lmax".format(ii)

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

                js = {
                    "now": new_temp,
                    "Heute höchster Wert": cmax,
                    "Heute tiefster Wert": cmin,
                    "Gestern höchster Wert": self._config.get(path_lmax, "n/A"),
                    "Gestern tiefster Wert": self._config.get(path_lmin, "n/A")
                }
                if new_temp != -1000 and self._prev_deg == -1000:
                    self.__client.publish(self._rh_topic.ava_topic, "online", retain=True)
                    self._sensor_humidity(js, keypath="now")
                elif new_temp != -1000:
                    self._sensor_humidity(js, keypath="now")
                else:
                    self.__client.publish(self._rh_topic.ava_topic, "offline", retain=True)
                self._prev_deg[1] = new_temp


        def send_update(self, force=False, insane=0):
            humidity, temperature = Adafruit_DHT.read_retry(
                self.dht,
                self._config.get("DHT/dev/pin",22)
            )
            humidity = round(humidity, ndigits=1)
            temperature = round(temperature, ndigits=1)

            self.sendTemperature(temperature, force)
            self.sendHumidity(humidity, force)

        def set_pluginManager(self, pm):
            self._plugin_manager = pm

class DhtConf:
    def __init__(self, conf: conf.BasicConfig):
        self.__ids = []
        self.c = conf

    def run(self):
        from Tools import ConsoleInputTools as cit
        self.c["DHT/dev/pin"] = cit.get_number_input("Pin Nummer von Datenpin? ", 22)
        self.c["DHT/dev/type"] = cit.get_input("DHT Type? Möglich ist 11 22 2302 ", "22")
        self.c["DHT/name"] = cit.get_input("Name für Hass ", True, "DHT")
        self.c["DHT/update_seconds"] = cit.get_number_input("Wie oft soll gemessen werden? ", 60)

