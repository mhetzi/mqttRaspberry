# -*- coding: utf-8 -*-
import datetime
import json
import logging
import threading
import time

import paho.mqtt.client as mclient
import schedule

import Mods.Weatherflow.UDP as wudp
import Tools.Autodiscovery as autodisc
import Tools.PluginManager
import Tools.ResettableTimer as rTimer
from Mods.Weatherflow.UpdateTypes import (DeviceStatus, HubStatus,
                                          LightningStrikeEvent, Obs_Sky,
                                          ObsAir, RainStart, RapidWind, Tools,
                                          updateType)
from Tools.Config import BasicConfig


class WeatherflowPlugin:

    @staticmethod
    def reset_daily_rain(self):
        self._logger.debug("Setze Täglichen Regenzähler & Temperatur Stats zurück...")
        self._config["Weatherflow/daily_rain"] = 0
        self._config["Weatherflow/temp_stats/min"] = "RESET"
        self._config["Weatherflow/temp_stats/max"] = "RESET"

    @staticmethod
    def get_device_online_topic(serial_number: str):
        return "device_online/weatherflow/{}/online".format(serial_number)

    @staticmethod
    def reset_hourly_rain(self):
        self._logger.debug("Setze Stündlichen Regenzähler zurück...")
        self._config["Weatherflow/hourly_rain"] = 0

    def __init__(self, client: mclient.Client, opts: BasicConfig, logger: logging.Logger, device_id: str):
        self._client = client
        self._config = opts
        self._logger = logger.getChild("Weatherflow")
        self._device_id = device_id
        self._udp = None
        self._timer = threading.Timer(2, self.check_online_status)
        self._lightning_counter = {"count": 0, "timer": None, "serial": None, "init": 0}
        self._raining_info = {}
        self._wind_info = {}
        self._online_states = {}
        self._sensor_errror = DeviceStatus.SensorStatus.OK
        self._pluginManager = None

    def set_pluginManager(self, pm):
        self._pluginManager = pm

    def register(self):
        if self._config.get("Weatherflow/deregister", False):
            self._config["Weatherflow/deregister"] = False
            for sens in self._config.get("Weatherflow/reg_sensor", []):
                self._client.publish(sens, "", retain=True)
            for ser in self._config.get("Weatherflow/serial_reg", []):
                online_topic = WeatherflowPlugin.get_device_online_topic(ser)
                self._client.publish(online_topic, "", retain=True)
            self._config["Weatherflow/reg_sensor"] = []
            self._config["Weatherflow/serial_reg"] = []
            self._config["Weatherflow/seen_devices"] = []
            self._config.save()

        self._logger.info("Starte UDP Server, um auf broadcasts von der Station lauschen zu können")
        self._udp = wudp.UdpServer(self._config.get("Weatherflow/broadcast_addr", "255.255.255.255"),
                                   self._config.get("Weatherflow/broadcast_port", 50222), logger=self._logger.getChild("UDP"))
        self._config.get("Weatherflow/events", True)
        self._udp.on_message = self.process_update

        self._udp.start()
        self._timer.start()

        self._logger.debug("Regestriere Schedule Jobs für Tägliche und Stündliche Reset Aufgaben...")
        schedule.every().day.at("00:00").do(WeatherflowPlugin.reset_daily_rain, self)
        schedule.every().hours.do(WeatherflowPlugin.reset_hourly_rain, self)

    def register_new_serial(self, serial):
        online_topic = WeatherflowPlugin.get_device_online_topic(serial)
        self._client.will_set(online_topic, "offline", retain=True)
        self._client.publish(online_topic, "online", retain=True)
        if serial not in self._config.get("Weatherflow/serial_reg", []):
            self._config["Weatherflow/serial_reg"].append(serial)

    def register_new_air(self, serial_number, update: ObsAir.ObsAir):
        deviceInfo = autodisc.DeviceInfo()
        deviceInfo.IDs = [serial_number]
        deviceInfo.mfr = "Weatherflow"
        deviceInfo.model = "Air"
        deviceInfo.name = "Weatherflow AIR"
        deviceInfo.sw_version = update.firmware_revision

        self._logger.info("Regestriere neue Air mit der Seriellen Nummer: {}".format(serial_number))
        self.register_new_serial(serial_number)
        self.register_new_sensor(serial_number, "Luftdruck", "station_pressure", "mb", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Temperatur", "air_temperature", "°C", autodisc.SensorDeviceClasses.TEMPERATURE, deviceInfo,
                                 value_template="{{ value_json.now }}", json_attributes=True)
        self.register_new_sensor(serial_number, "Relative Luftfeuchte", "relative_humidity", "%", autodisc.SensorDeviceClasses.HUMIDITY, deviceInfo)
        self.register_new_sensor(serial_number, "Blitze", "lightning_count", "Stk.", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Durchschnittliche Blitz entfernung", "lightning_dist", "km", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Batterie (AIR)", "battery", "V", autodisc.SensorDeviceClasses.BATTERY, deviceInfo,
                                value_template="{{ value_json.now }}", json_attributes=True)

        if self._config["Weatherflow/events"]:
            self.register_new_sensor(serial_number, "Blitz Entfernung", "lightning_last_dist", "km", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
            self.register_new_sensor(serial_number, "Blitz Energie", "lightning_last_nrg", "", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
            self.register_new_sensor(serial_number, "Es Blitzt", "es_blitzt", "", autodisc.BinarySensorDeviceClasses.POWER, deviceInfo)

            self.update_sensor(serial_number, "lightning_last_dist", "0", autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(serial_number, "lightning_last_nrg", "0", autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(serial_number, "es_blitzt", 0, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)

    def register_new_sky(self, serial_number, upd: Obs_Sky.ObsSky):
        deviceInfo = autodisc.DeviceInfo()
        deviceInfo.IDs = [serial_number]
        deviceInfo.mfr = "Weatherflow"
        deviceInfo.model = "Sky"
        deviceInfo.name = "Weatherflow SKY"
        deviceInfo.sw_version = upd.firmware_revision

        self._logger.info("Regestriere neue Sky mit der Seriellen Nummer: {}".format(serial_number))
        self.register_new_serial(serial_number)
        self.register_new_sensor(serial_number, "Lux", "lux", "lux", autodisc.SensorDeviceClasses.ILLUMINANCE, deviceInfo)
        self.register_new_sensor(serial_number, "UV Index", "uv_index", "uv", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Regen", "accumulated_rain", "mm", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Wind Max", "wind_gust", "m/s", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Wind avg", "wind_average", "m/s", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Wind Min", "wind_lull", "m/s", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Wind Richtung", "wind_direction", "°", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Batterie (SKY)", "battery_sky", "V", autodisc.SensorDeviceClasses.BATTERY, deviceInfo,
                                value_template="{{ value_json.now }}", json_attributes=True)
        self.register_new_sensor(serial_number, "Sonnen einstrahlung", "solar_radiation", "w/m²", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Täglicher Regen", "local_day_rain_accumulation", "mm", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Stündlicher Regen", "local_hour_rain_accumulation", "mm",
                                 autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.update_sensor(serial_number, "local_day_rain_accumulation", self._config.get("Weatherflow/daily_rain", 0), autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(serial_number, "local_hour_rain_accumulation", self._config.get("Weatherflow/hourly_rain", 0),
                           autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)

        if self._config["Weatherflow/events"]:
            self.register_new_sensor(serial_number, "Regen", "raining", "", autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
            self.register_new_sensor(serial_number, "Windig", "windy", "", autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
            self.update_sensor(serial_number, "raining", 0, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(serial_number, "windy", 0, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)

    def register_new_sensor(self, serial_number, visible_name, name, messurement_value, device_class: autodisc.DeviceClass, devInf: autodisc.DeviceInfo, value_template=None, json_attributes=None):
        topic = self._config.get_autodiscovery_topic(autodisc.Component.SENSOR, name, device_class, node_id=serial_number)
        online_topic = WeatherflowPlugin.get_device_online_topic(serial_number)
        payload = topic.get_config_payload(visible_name, messurement_value, online_topic, value_template=value_template, json_attributes=json_attributes)
        self._logger.info(
            "Neuen Sensor ({}) regestriert. Folgendes ist die Config Payload: {}".format(visible_name, payload))
        self._client.publish(topic.config, payload, retain=True)
        self._logger.info("Neuen Sensor ({}) regestriert. Folgendes ist die Config Payload: {}".format(visible_name, payload))
        if topic.config not in self._config.get("Weatherflow/reg_sensor", []):
            self._config["Weatherflow/reg_sensor"].append(topic.config)

    def update_sensor(self, serial_number, name, value, device_class: autodisc.DeviceClass):  # IMPLEMET FERTIG MACHEN
        topic = self._config.get_autodiscovery_topic(autodisc.Component.SENSOR, name, device_class, node_id=serial_number)
        self._client.publish(topic.state, value)

    def update_is_raining(self, serial, is_raining=False):
        if is_raining and self._config["Weatherflow/events"]:
            self.update_sensor(serial, "raining", 1, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            if self._raining_info.get(serial, None) is None:
                self._raining_info[serial] = rTimer.ResettableTimer(120, self.update_is_raining, serial)
            else:
                self._raining_info[serial].reset()
        else:
            self.update_sensor(serial, "raining", 0, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            self._raining_info[serial] = None

    def update_is_windy(self, serial, is_windy=False, km=None, deg=None):
        if km == 0 and deg == 0:
            return
        if is_windy and self._config["Weatherflow/events"]:
            self.update_sensor(serial, "windy", 1, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            if self._wind_info.get(serial, None) is None:
                self._wind_info[serial] = rTimer.ResettableTimer(60, self.update_is_windy, serial)
            else:
                self._wind_info[serial].reset()
        else:
            self.update_sensor(serial, "windy", 0, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            self._wind_info[serial] = None

    def stop(self):
        if self._udp is not None:
            self._udp.shutdown()
        if self._timer is not None:
            self._timer.cancel()
        self._timer = None

        for k in self._raining_info.keys():
            if self._raining_info[k] is not None:
                self._raining_info[k].cancel()

        for k in self._wind_info.keys():
            if self._wind_info[k] is not None:
                self._wind_info[k].cancel()

    def process_update(self, update: dict):
        pupd = Tools.parse_json_to_update(update)
        if pupd is None:
            self._logger.info("Nachricht {} von Station ist kein update.".format(update))
            return
        #self._logger.debug("Habe von Station {} update bekommen. Nachricht war: {}".format(pupd.update_type.name, update))

        if pupd.update_type == updateType.UpdateType.DeviceStatus:
            self._sensor_errror = pupd.sensor_status
            self.set_lastseen_device(pupd.serial_number, 1, True)
        elif pupd.update_type == updateType.UpdateType.ObsAir:
            self.process_obs_air(pupd)
        elif pupd.update_type == updateType.UpdateType.ObsSky:
            self.process_obs_sky(pupd)
        elif pupd.update_type == updateType.UpdateType.LightningStrikeEvent:
            self._logger.info("Air sagt es blitzt!")
            if not self._config["Weatherflow/events"]:
                self._logger.debug("Keine events erlaubt")
                return

            self.update_sensor(pupd.serial_number, "lightning_last_dist", pupd.distance, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(pupd.serial_number, "lightning_last_nrg", pupd.energy, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(pupd.serial_number, "es_blitzt", 1, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)

            if self._lightning_counter["serial"] is None:
                self._lightning_counter["serial"] = pupd.serial_number
                self._logger.debug("Seriennummer des Blitzmeldenden Gerätes kopiert")
            if self._lightning_counter["serial"] == pupd.serial_number:
                self._lightning_counter["count"] += 1
                if self._lightning_counter["timer"] is None:
                    self._lightning_counter["timer"] = threading.Timer(60, self.count_lightnings_per_minute)
                    self._lightning_counter["timer"].start()
                    self._logger.info("Blitz Timer gestartet")
                else:
                    self._logger.info("Kein Blitztimer gestartert")
            else:
                self._logger.warn("Serienummern nicht gleich!")

        elif pupd.update_type == updateType.UpdateType.RainStart:
            self._logger.info("Sky sagt es regnet!")
            self.update_is_raining(pupd.serial_number, True)
        elif pupd.update_type == updateType.UpdateType.RapidWind:
            #self._logger.info("Sky sagt es geht der wind {}m/s Richtung {}°".format(pupd.wind_speed, pupd.wind_direction))
            self.update_is_windy(pupd.serial_number, True, pupd.wind_speed, pupd.wind_direction)

    def set_lastseen_device(self, serial_number: str, interval: int, no_register=False) -> bool:
        if self._online_states.get(serial_number, None) is None and not no_register:
            self._logger.info("Muss für {} neuen Online Status erstellen...".format(serial_number))
            self._online_states[serial_number] = {}
            self._online_states[serial_number]["lastUpdate"] = datetime.datetime.now()
            self._online_states[serial_number]["intervall"] = interval
            self._online_states[serial_number]["error"] = DeviceStatus.SensorStatus.OK
            self._online_states[serial_number]["wasOnline"] = True
        if serial_number not in self._config.get("Weatherflow/seen_devices", []):
            self._logger.info("Ist unbekanntes Gerät.")
            if not no_register:
                self._config["Weatherflow/seen_devices"].append(serial_number)
                self._logger.info("Speichere als gesehenes Gerät.")
            return False
        elif no_register:
            return False
        self._online_states[serial_number]["lastUpdate"] = datetime.datetime.now()
        self._online_states[serial_number]["intervall"] = interval
        return True

    def process_obs_air(self, update: ObsAir.ObsAir):
        if not self.set_lastseen_device(update.serial_number, update.report_intervall_minutes):
            self.register_new_air(update.serial_number, update)

        tendenz = "Tendenz: Keine"

        if self._config.get("Weatherflow/temp_stats/min", "RESET") == "RESET":
            self._config["Weatherflow/temp_stats/min"] = update.air_temperatur
        elif self._config["Weatherflow/temp_stats/min"] > update.air_temperatur:
            self._config["Weatherflow/temp_stats/min"] = update.air_temperatur
            tendenz = "Tendenz: Fallend"

        if self._config.get("Weatherflow/temp_stats/max", "RESET") == "RESET":
            self._config["Weatherflow/temp_stats/max"] = update.air_temperatur
        elif self._config["Weatherflow/temp_stats/max"] < update.air_temperatur:
            self._config["Weatherflow/temp_stats/max"] = update.air_temperatur
            tendenz = "Tendenz: Steigend"


        temperature_json = {"min": self._config["Weatherflow/temp_stats/min"],
                            "max": self._config["Weatherflow/temp_stats/max"], "now": update.air_temperatur, "tendenz": tendenz}

        self.update_sensor(update.serial_number, "station_pressure", update.station_pressure, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "air_temperature", json.dumps(temperature_json), autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "relative_humidity", update.relative_humidity, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "lightning_count", update.lightning_strike_count, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "lightning_dist", update.lightning_strike_avg_distance, autodisc.SensorDeviceClasses.GENERIC_SENSOR)

        if update.lightning_strike_count == 0 and not self._config["Weatherflow/events"]:
            self.update_sensor(update.serial_number, "lightning_last_dist", "0", autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(update.serial_number, "lightning_last_nrg", "0", autodisc.SensorDeviceClasses.GENERIC_SENSOR)

        if self._sensor_errror == DeviceStatus.SensorStatus.OK:
            battery_str = update.battery
        elif self._sensor_errror == DeviceStatus.SensorStatus.AIR_LIGHTNING_DISTURBER:
            battery_str = update.battery
        elif self._sensor_errror == DeviceStatus.SensorStatus.AIR_LIGHTNING_FAILED:
            battery_str = "Blitzsensor ist ausgefallen"
        elif self._sensor_errror == DeviceStatus.SensorStatus.AIR_LIGHTNING_NOISE:
            battery_str = "Zu viel Rauschen für Blitzsensor"
        elif self._sensor_errror == DeviceStatus.SensorStatus.AIR_PRESSURE_FAILED:
            battery_str = "Luftdrucksensor ausgefallen"
        elif self._sensor_errror == DeviceStatus.SensorStatus.AIR_TEMPERATURE_FAILED:
            battery_str = "Temperatursensor ausgefallen"
        elif self._sensor_errror == DeviceStatus.SensorStatus.AIR_RH_FAILED:
            battery_str = "Luftfeuchtesensor ausgefallen"
        else:
            battery_str = update.battery

        if self._config.get("Weatherflow/{0}/minBat".format(update.serial_number), 10) > update.battery:
            self._config["Weatherflow/{0}/minBat".format(update.serial_number)] = update.battery
        elif self._config.get("Weatherflow/{0}/maxBat".format(update.serial_number), 0) < update.battery:
            self._config["Weatherflow/{0}/maxBat".format(update.serial_number)] = update.battery
        battery_json = {
                        "min": self._config.get("Weatherflow/{0}/minBat".format(update.serial_number), 0),
                        "max": self._config.get("Weatherflow/{0}/maxBat".format(update.serial_number), 0),
                        "now": battery_str
                        }
        self.update_sensor(update.serial_number, "battery", json.dumps(battery_json), autodisc.SensorDeviceClasses.BATTERY)

    def process_obs_sky(self, update: Obs_Sky.ObsSky):
        if not self.set_lastseen_device(update.serial_number, update.report_interval_minutes):
            self.register_new_sky(update.serial_number, update)

        self._config["Weatherflow/daily_rain"] += update.accumulated_rain
        self._config["Weatherflow/hourly_rain"] += update.accumulated_rain

        self.update_sensor(update.serial_number, "lux", update.lux, autodisc.SensorDeviceClasses.ILLUMINANCE)
        self.update_sensor(update.serial_number, "uv_index", update.uv_index, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "accumulated_rain", update.accumulated_rain, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "wind_gust", update.wind_gust, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "wind_average", update.wind_avg, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "wind_lull", update.wind_lull, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "wind_direction", update.wind_direction, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "solar_radiation", update.solar_radiation, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "local_day_rain_accumulation", self._config["Weatherflow/daily_rain"], autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "local_hour_rain_accumulation", self._config["Weatherflow/hourly_rain"], autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
        self.update_is_windy(update.serial_number, True, update.wind_avg, update.wind_direction)

        if update.rain_type is not None and update.rain_type == "hail":
            battery_str = "Hagel"
            self._logger.info("Reporting Battery as hail")
        elif self._sensor_errror == DeviceStatus.SensorStatus.OK:
            battery_str = str(update.battery)
            self._logger.info("Reporting Battery {} because there are no errors.".format(update.battery))
        elif self._sensor_errror == DeviceStatus.SensorStatus.SKY_LIGHT_UV_FAILED:
            battery_str = "UV Sensor ist ausgefallen"
        elif self._sensor_errror == DeviceStatus.SensorStatus.SKY_PRECIP_FAILED:
            battery_str = "Regen Sensor ist ausgefallen"
        elif self._sensor_errror == DeviceStatus.SensorStatus.SKY_WIND_FAILED:
            battery_str = "Wind Sensor ist ausgefallen"
        else:
            battery_str = str(update.battery)
            self._logger.info("Reporting Battery {} because there are unknown errors.".format(update.battery))

        if update.rain_type != 0:
            self._logger.info("rain_type: {}".format(update.rain_type))
            self.update_is_raining(update.serial_number, True)
    
        if self._config.get("Weatherflow/{0}/minBat".format(update.serial_number), 10) > update.battery:
            self._config["Weatherflow/{0}/minBat".format(update.serial_number)] = update.battery
        elif self._config.get("Weatherflow/{0}/maxBat".format(update.serial_number), 0) < update.battery:
            self._config["Weatherflow/{0}/maxBat".format(update.serial_number)] = update.battery
        
        battery_json = {
                        "min": self._config.get("Weatherflow/{0}/minBat".format(update.serial_number), 0),
                        "max": self._config.get("Weatherflow/{0}/maxBat".format(update.serial_number), 0),
                        "now": battery_str
                        }
        self.update_sensor(update.serial_number, "battery_sky", json.dumps(battery_json), autodisc.SensorDeviceClasses.BATTERY)


    def count_lightnings_per_minute(self):
        count = self._lightning_counter["count"]
        self._lightning_counter["count"] = 0
        if self._lightning_counter["init"] == 0 and self._lightning_counter["serial"] is not None:
            self._logger.info("Es Blitzt, Regestriere Blitze pro Minute zähler für {}".format(self._lightning_counter["serial"]))
            self.register_new_sensor(self._lightning_counter["serial"], "Blitze in der Minute", "lightning_count_min", "Stk/Min", autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            self._lightning_counter["init"] = 1
        if 0 < self._lightning_counter["init"] <= 10:
            if count == 0:
                self._lightning_counter["init"] += 1
            else:
                self._lightning_counter["init"] = 1
            self._lightning_counter["timer"] = threading.Timer(60, self.count_lightnings_per_minute)
            self._lightning_counter["timer"].start()
            self._logger.debug("Es blitzt immer nocht. Restarte timer...")
            self.update_sensor(self._lightning_counter["serial"], "es_blitzt", 1, autodisc.BinarySensorDeviceClasses.POWER)
        elif self._lightning_counter["init"] > 5:
            self._lightning_counter["timer"] = None
            self._logger.debug("Es blitzt nicht mehr. Timer wird nicht neu gestartet...")
            self.update_sensor(self._lightning_counter["serial"], "es_blitzt", 0, autodisc.BinarySensorDeviceClasses.POWER)

        if self._lightning_counter["serial"] is not None:
            self.update_sensor(self._lightning_counter["serial"], "lightning_count_min", count, autodisc.SensorDeviceClasses.GENERIC_SENSOR)

    def check_online_status(self):
        if self._timer is not None:
            self._timer.cancel()

        for serial in self._online_states.keys():
            last_update = self._online_states[serial]["lastUpdate"]
            timespan = datetime.datetime.now() - last_update
            if (timespan.seconds / 60) > (self._online_states[serial]["intervall"] + 10) and self._online_states[serial]["wasOnline"]:
                self._logger.info("Weatherflow Device {} ist jetzt offline".format(serial))
                online_topic = WeatherflowPlugin.get_device_online_topic(serial)
                self._client.publish(online_topic, "offline", retain=True)
                self._online_states[serial]["wasOnline"] = False
            elif not self._online_states[serial]["wasOnline"]:
                self._logger.info("Weatherflow Device {} ist jetzt online".format(serial))
                online_topic = WeatherflowPlugin.get_device_online_topic(serial)
                self._client.publish(online_topic, "online", retain=True)
                self._online_states[serial]["wasOnline"] = True

        if self._timer is not None:
            self._timer.cancel()
            self._timer = threading.Timer(30, self.check_online_status)
            self._timer.start()
