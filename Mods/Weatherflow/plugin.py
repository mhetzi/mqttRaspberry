# -*- coding: utf-8 -*-
import datetime
import json
import logging
import threading
import time
import math
from typing import Union

import paho.mqtt.client as mclient
import schedule

import Mods.Weatherflow.UDP as wudp
import Tools.Autodiscovery as autodisc
import Tools.PluginManager
import Tools.ResettableTimer as rTimer
from Mods.Weatherflow.UpdateTypes import (DeviceStatus, HubStatus,
                                          LightningStrikeEvent, Obs_Sky,
                                          ObsAir, RainStart, RapidWind, Tools, ObsTempest,
                                          updateType)
from Tools.Config import BasicConfig

class WeatherflowPlugin:

    @staticmethod
    def percentageMinMax(input, min, max):
        return ((input - min) * 100) / (max - min)

    @staticmethod
    def reset_daily_rain(self):
        self._logger.debug("Setze Täglichen Regenzähler & Temperatur Stats zurück...")
        self._config["Weatherflow/yesterday_daily_rain"] = self._config["Weatherflow/daily_rain"]
        self._config["Weatherflow/daily_rain"] = 0
        self._config["Weatherflow/temp_stats/lmin"] = self._config.get("Weatherflow/temp_stats/min", "n/A")
        self._config["Weatherflow/temp_stats/lmax"] = self._config.get("Weatherflow/temp_stats/max", "n/A")

        self._config["Weatherflow/temp_stats/min"] = "RESET"
        self._config["Weatherflow/temp_stats/max"] = "RESET"

    @staticmethod
    def get_device_online_topic(serial_number: str):
        return "device_online/weatherflow/{}/online".format(serial_number)

    @staticmethod
    def reset_hourly_rain(self):
        self._logger.debug("Setze Stündlichen Regenzähler zurück...")
        self._config["Weatherflow/hourly_rain"] = 0
        delta = datetime.timedelta(hours=1)
        if self._lightning_counter["lastTime"] < datetime.datetime.now() - delta:
            self._logger.debug("Prüfe Blitzmelder")
            if self._lightning_counter["serial"] is None:
                self._lightning_counter["init"] = 100
                self.count_lightnings_per_minute()

    def __init__(self, client: mclient.Client, opts: BasicConfig, logger: logging.Logger, device_id: str):
        self._client = client
        self._config = opts
        self._logger = logger.getChild("Weatherflow")
        self._device_id = device_id
        self._udp = None
        self._timer = threading.Timer(2, self.check_online_status)
        self._lightning_counter = {"count": 0, "timer": None, "serial": None, "init": 0, "lastTime": datetime.datetime.now()}
        self._raining_info = {}
        self._wind_info = {}
        self._online_states = {}
        self._pluginManager = None
        self._deviceUpdates = {}
        self.wasWindy = 0

        self._wind_filter = {
            "avg": -1, "max": -1, "min": -1, "temp": -1
        }

        if self._config.get("Weatherflow/wind_diff", None) is None:
            self._config["Weatherflow/wind_diff"] = 0.2

        if self._config.get("Weatherflow/temp_diff", None) is None:
            self._config["Weatherflow/temp_diff"] = 0.2


    def set_pluginManager(self, pm):
        self._pluginManager = pm

    def sendStates(self):
        self._wind_filter = {
            "avg": -1, "max": -1, "min": -1, "temp": -1
        }

    def register(self, wasConnected=False):
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

        if not wasConnected:
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
        self._client.publish(online_topic, "online", retain=True)
        if serial not in self._config.get("Weatherflow/serial_reg", []):
            self._config["Weatherflow/serial_reg"].append(serial)

    def register_new_air(self, serial_number, update: Union[ObsAir.ObsAir, ObsTempest.ObsTempest], tempest_device=None):
        deviceInfo = autodisc.DeviceInfo()
        deviceInfo.IDs = [serial_number]
        deviceInfo.mfr = "Weatherflow"
        deviceInfo.model = "Air"
        deviceInfo.name = "Weatherflow AIR"
        deviceInfo.sw_version = update.firmware_revision
        if tempest_device is not None:
            deviceInfo = tempest_device
        std_dev = autodisc.Topics.get_std_devInf()
        
        if len(std_dev.IDs) > 0:
            deviceInfo.via_device = std_dev.IDs[0]
        else:
            self._logger.info("Kein std Device gefunden. Kann kein via erstellen!")


        self._logger.info("Regestriere neue Air mit der Seriellen Nummer: {}".format(serial_number))
        self.register_new_serial(serial_number)
        self.register_new_sensor(serial_number, "Luftdruck", "station_pressure", "mb", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Temperatur", "air_temperature", "°C", autodisc.SensorDeviceClasses.TEMPERATURE, deviceInfo,
                                 value_template="{{ value_json.now }}", json_attributes=True)
        self.register_new_sensor(serial_number, "Relative Luftfeuchte", "relative_humidity", "%", autodisc.SensorDeviceClasses.HUMIDITY, deviceInfo)
        self.register_new_sensor(serial_number, "Blitze", "lightning_count", "Stk.", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Durchschnittliche Blitz entfernung", "lightning_dist", "km", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Batterie (AIR)", "battery", "%", autodisc.SensorDeviceClasses.BATTERY, deviceInfo,
                                value_template="{{ value_json.now }}", json_attributes=True)

        if self._config["Weatherflow/events"]:
            self.register_new_sensor(serial_number, "Blitz Entfernung", "lightning_last_dist", "km", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
            self.register_new_sensor(serial_number, "Blitz Energie", "lightning_last_nrg", "", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
            self.register_new_sensor(serial_number, "Es Blitzt", "es_blitzt", "", autodisc.BinarySensorDeviceClasses.POWER, deviceInfo)
            self.register_new_sensor(serial_number, "Blitze in der Minute", "lightning_count_min", "Stk/Min", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)

            self.update_sensor(serial_number, "lightning_last_dist", "0", autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(serial_number, "lightning_last_nrg", "0", autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(serial_number, "es_blitzt", 0, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(serial_number, "lightning_count_min", 0, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)


    def register_new_sky(self, serial_number, upd: Union[Obs_Sky.ObsSky, ObsTempest.ObsTempest], tempest_device=None):
        deviceInfo = autodisc.DeviceInfo()
        deviceInfo.IDs = [serial_number]
        deviceInfo.mfr = "Weatherflow"
        deviceInfo.model = "Sky"
        deviceInfo.name = "Weatherflow SKY"
        deviceInfo.sw_version = upd.firmware_revision

        if tempest_device is not None:
            deviceInfo = tempest_device

        std_dev = autodisc.Topics.get_std_devInf()
        
        if len(std_dev.IDs) > 0:
            deviceInfo.via_device = std_dev.IDs[0]
        else:
            self._logger.info("Kein std Device gefunden. Kann kein via erstellen!")

        self._logger.info("Regestriere neue Sky mit der Seriellen Nummer: {}".format(serial_number))
        self.register_new_serial(serial_number)
        self.register_new_sensor(serial_number, "Lux", "lux", "lux", autodisc.SensorDeviceClasses.ILLUMINANCE, deviceInfo)
        self.register_new_sensor(serial_number, "UV Index", "uv_index", "uv", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Regen", "accumulated_rain", "mm", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Wind Max", "wind_gust", "m/s", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo,
                                value_template="{{ value_json.ms }}", json_attributes=True)
        self.register_new_sensor(serial_number, "Wind avg", "wind_average", "m/s", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo,
                                value_template="{{ value_json.ms }}", json_attributes=True)
        self.register_new_sensor(serial_number, "Wind Min", "wind_lull", "m/s", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo,
                                value_template="{{ value_json.ms }}", json_attributes=True)
        self.register_new_sensor(serial_number, "Wind Richtung", "wind_direction", "°", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Batterie (SKY)", "battery_sky", "%", autodisc.SensorDeviceClasses.BATTERY, deviceInfo,
                                value_template="{{ value_json.now }}", json_attributes=True)
        self.register_new_sensor(serial_number, "Sonnen einstrahlung", "solar_radiation", "w/m²", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.register_new_sensor(serial_number, "Täglicher Regen", "local_day_rain_accumulation", "mm", autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo,
                                json_attributes=True, value_template="{{ value_json.today }}")
        self.register_new_sensor(serial_number, "Stündlicher Regen", "local_hour_rain_accumulation", "mm",
                                 autodisc.SensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
        self.update_sensor(serial_number, "local_day_rain_accumulation", self._config.get("Weatherflow/daily_rain", 0), autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(serial_number, "local_hour_rain_accumulation", self._config.get("Weatherflow/hourly_rain", 0),
                           autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)

        if self._config["Weatherflow/events"]:
            self.register_new_sensor(serial_number, "Regen", "raining", "", autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR, deviceInfo, 
                value_template="{{ value_json.Regen }}", json_attributes=True)
            self.register_new_sensor(serial_number, "Windig", "windy", "", autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR, deviceInfo)
            self.update_sensor(
                serial_number,
                "raining", 
                json.dumps({"Regen": 0,"Hagel": "Nein" }),
                autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR
            )
            self.update_sensor(serial_number, "windy", 0, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)

    def register_new_sensor(self, serial_number, visible_name, name, messurement_value, device_class: autodisc.DeviceClass, devInf: autodisc.DeviceInfo, value_template=None, json_attributes=None):
        topic = self._config.get_autodiscovery_topic(autodisc.Component.SENSOR, name, device_class, node_id=serial_number)
        online_topic = WeatherflowPlugin.get_device_online_topic(serial_number)

        uID = "{}.wf-{}.{}".format( "binary_sensor" if isinstance(device_class, autodisc.BinarySensorDeviceClasses) else "sensor", serial_number, name )

        payload = topic.get_config_payload(visible_name, messurement_value, online_topic, value_template=value_template, json_attributes=json_attributes, device=devInf, unique_id=uID)
        self._logger.info(
            "Neuen Sensor ({}) regestriert. Folgendes ist die Config Payload: {}".format(visible_name, payload))
        self._client.publish(topic.config, payload, retain=True)
        self._logger.info("Neuen Sensor ({}) regestriert. Folgendes ist die Config Payload: {}".format(visible_name, payload))
        if topic.config not in self._config.get("Weatherflow/reg_sensor", []):
            self._config["Weatherflow/reg_sensor"].append(topic.config)

    def update_sensor(self, serial_number, name, value, device_class: autodisc.DeviceClass):
        topic = self._config.get_autodiscovery_topic(autodisc.Component.SENSOR, name, device_class, node_id=serial_number)
        if isinstance(value, dict):
            value = json.dumps(value)
        self._client.publish(topic.state, value)

    def update_is_raining(self, serial, is_raining=False, is_hail=False):
        rain_json = {
            "Regen": 1 if is_raining else 0,
            "Hagel": "Ja" if is_hail else "Nein" 
        }
        if is_raining and self._config["Weatherflow/events"]:
            self.update_sensor(serial, "raining", json.dumps(rain_json), autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            if self._raining_info.get(serial, None) is None:
                self._raining_info[serial] = rTimer.ResettableTimer(360, self.update_is_raining, serial)
            else:
                self._raining_info[serial].reset()
        else:
            self.update_sensor(serial, "raining", json.dumps(rain_json), autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            self._raining_info[serial] = None

    def update_is_windy(self, serial, is_windy=False, km=None, deg=None):
        if km == 0 and deg == 0:
            return
        if is_windy and self._config["Weatherflow/events"]:
            self.wasWindy += 1
            if self.wasWindy == 1:
                self.update_sensor(serial, "windy", 1, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            elif self.wasWindy > 120:
                self.wasWindy = 0

            if self._wind_info.get(serial, None) is None:
                self._wind_info[serial] = rTimer.ResettableTimer(60, self.update_is_windy, serial)
            else:
                self._wind_info[serial].reset()
        else:
            self.update_sensor(serial, "windy", 0, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            self.wasWindy = 0
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

        pupd = Tools.parse_json_to_update(update, self._logger)
        if pupd is None:
            self._logger.info("Nachricht {} von Station ist kein update.".format(update))
            return
        self._logger.debug("Habe von Station {} update bekommen. Nachricht war: {}".format(pupd.update_type.name, update))

        if pupd.update_type == updateType.UpdateType.DeviceStatus:
            self._deviceUpdates[pupd.serial_number] = pupd
            self._logger.debug(update)
            self.set_lastseen_device(pupd.serial_number, 1, True)
        elif pupd.update_type == updateType.UpdateType.ObsAir:
            self.process_obs_air(pupd)
        elif pupd.update_type == updateType.UpdateType.ObsSky:
            self.process_obs_sky(pupd)
        elif pupd.update_type == updateType.UpdateType.ObsTempest:
            if not self.set_lastseen_device(pupd.serial_number, pupd.report_interval_minutes):
                deviceInfo = autodisc.DeviceInfo()
                deviceInfo.IDs = [pupd.serial_number]
                deviceInfo.mfr = "Weatherflow"
                deviceInfo.model = "Tempest"
                deviceInfo.name = "Weatherflow Tempest"
                deviceInfo.sw_version = pupd.firmware_revision
                self.register_new_air(pupd.serial_number, pupd, deviceInfo)
                self.register_new_sky(pupd.serial_number, pupd, deviceInfo)
            self.process_obs_air(pupd)
            self.process_obs_sky(pupd)
        elif pupd.update_type == updateType.UpdateType.LightningStrikeEvent:
            self._logger.info("Air sagt es blitzt!")
            if not self._config["Weatherflow/events"]:
                self._logger.debug("Keine events erlaubt")
                return

            self.update_sensor(pupd.serial_number, "lightning_last_dist", pupd.distance, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(pupd.serial_number, "lightning_last_nrg", pupd.energy, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(pupd.serial_number, "es_blitzt", 1, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            self._lightning_counter["lastTime"] = datetime.datetime.now()
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

    def set_lastseen_device(self, serial_number: str, interval_minutes: int, no_register=False) -> bool:
        interval = interval_minutes * 60
        if self._online_states.get(serial_number, None) is None and not no_register:
            self._logger.info("Muss für {} neuen Online Status erstellen...".format(serial_number))
            self._online_states[serial_number] = {}
            self._online_states[serial_number]["lastUpdate"] = datetime.datetime.now()
            self._online_states[serial_number]["intervall"] = interval
            self._online_states[serial_number]["error"] = DeviceStatus.SensorStatus.OK
            self._online_states[serial_number]["wasOnline"] = False
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

    def process_obs_air(self, update: Union[ObsAir.ObsAir, ObsTempest.ObsTempest]):
        max_delta = datetime.timedelta( minutes=(update.report_intervall_minutes * 2) )
        if (update.timestamp + max_delta) < datetime.datetime.now():
            self._logger.warning("Air Update wird abgewiesen. Zu alt! {}".format(update.timestamp.isoformat()))
            return
        self._logger.debug("Air update")
        if not self.set_lastseen_device(update.serial_number, update.report_intervall_minutes):
            self.register_new_air(update.serial_number, update)

        if self._config.get("Weatherflow/temp_stats/min", "RESET") == "RESET":
            self._config["Weatherflow/temp_stats/min"] = update.air_temperatur
        elif self._config["Weatherflow/temp_stats/min"] > update.air_temperatur:
            self._config["Weatherflow/temp_stats/min"] = update.air_temperatur

        if self._config.get("Weatherflow/temp_stats/max", "RESET") == "RESET":
            self._config["Weatherflow/temp_stats/max"] = update.air_temperatur
        elif self._config["Weatherflow/temp_stats/max"] < update.air_temperatur:
            self._config["Weatherflow/temp_stats/max"] = update.air_temperatur


        temperature_json = {"Heute Min": self._config["Weatherflow/temp_stats/min"],
                            "Heute Max": self._config["Weatherflow/temp_stats/max"],
                            "now": round(update.air_temperatur, 1),
                            "Gestern Min": self._config.get("Weatherflow/temp_stats/lmin", "n/A"),
                            "Gestern Max": self._config.get("Weatherflow/temp_stats/lmax", "n/A"),
                            }

        self.update_sensor(update.serial_number, "station_pressure", update.station_pressure, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        
        if self._config.get("Weatherflow/temp_diff", None) is not None:
            diff = self._config["Weatherflow/temp_diff"]
            if update.air_temperatur > (self._wind_filter["temp"] + diff) or update.air_temperatur < (self._wind_filter["temp"] - diff):
                self._wind_filter["temp"] = update.air_temperatur
                self.update_sensor(update.serial_number, "air_temperature", temperature_json, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        else:
            self.update_sensor(update.serial_number, "air_temperature", temperature_json, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "relative_humidity", update.relative_humidity, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "lightning_count", update.lightning_strike_count, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "lightning_dist", update.lightning_strike_avg_distance, autodisc.SensorDeviceClasses.GENERIC_SENSOR)

        if update.lightning_strike_count == 0 and not self._config["Weatherflow/events"]:
            self.update_sensor(update.serial_number, "lightning_last_dist", "0", autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            self.update_sensor(update.serial_number, "lightning_last_nrg", "0", autodisc.SensorDeviceClasses.GENERIC_SENSOR)

        if update.serial_number in self._deviceUpdates.keys():
            battery_str = math.floor(WeatherflowPlugin.percentageMinMax(update.battery, 1.6, 2.95))
            if isinstance(update, ObsTempest.ObsTempest):
                battery_str = 100
            sensor_ok = ""
            if self._deviceUpdates[update.serial_number]._sensor_status == DeviceStatus.SensorStatus.OK:
                sensor_ok = "OK"
            elif self._deviceUpdates[update.serial_number]._sensor_status & DeviceStatus.SensorStatus.AIR_LIGHTNING_DISTURBER:
                sensor_ok = "OK_LD"
            else:
                if self._deviceUpdates[update.serial_number]._sensor_status & DeviceStatus.SensorStatus.AIR_LIGHTNING_FAILED:
                    sensor_ok = str(sensor_ok) + "Blitzsensor ist ausgefallen. "
                if self._deviceUpdates[update.serial_number]._sensor_status & DeviceStatus.SensorStatus.AIR_LIGHTNING_NOISE:
                    sensor_ok = str(sensor_ok) + "Zu viel Rauschen für Blitzsensor. "
                if self._deviceUpdates[update.serial_number]._sensor_status & DeviceStatus.SensorStatus.AIR_PRESSURE_FAILED:
                    sensor_ok = str(sensor_ok) + "Luftdrucksensor ausgefallen. "
                if self._deviceUpdates[update.serial_number]._sensor_status & DeviceStatus.SensorStatus.AIR_TEMPERATURE_FAILED:
                    sensor_ok = str(sensor_ok) + "Temperatursensor ausgefallen. "
                if self._deviceUpdates[update.serial_number]._sensor_status & DeviceStatus.SensorStatus.AIR_RH_FAILED:
                    sensor_ok = str(sensor_ok) + "Luftfeuchtesensor ausgefallen. "

        if self._config.get("Weatherflow/{0}/minBat".format(update.serial_number), 10) > update.battery:
            self._config["Weatherflow/{0}/minBat".format(update.serial_number)] = update.battery
        elif self._config.get("Weatherflow/{0}/maxBat".format(update.serial_number), 0) < update.battery:
            self._config["Weatherflow/{0}/maxBat".format(update.serial_number)] = update.battery

        rssi = -100
        try:
            rssi = self._deviceUpdates[update.serial_number]._rssi
        except:
            pass

        battery_json = {
                        "min": self._config.get("Weatherflow/{0}/minBat".format(update.serial_number), 0),
                        "max": self._config.get("Weatherflow/{0}/maxBat".format(update.serial_number), 0),
                        "now": battery_str,
                        "volt": update.battery,
                        "rssi": rssi,
                        "sensors": sensor_ok
                        }
        self.update_sensor(update.serial_number, "battery", battery_json, autodisc.SensorDeviceClasses.BATTERY)

    def process_obs_sky(self, update: Union[Obs_Sky.ObsSky, ObsTempest.ObsTempest]):
        max_delta = datetime.timedelta(minutes=(update.report_intervall_minutes * 2) )
        if (update.timestamp + max_delta) < datetime.datetime.now():
            self._logger.warning("Sky Update wird abgewiesen. Zu alt!")
            return
        self._logger.debug("Sky update")
        if not self.set_lastseen_device(update.serial_number, update.report_interval_minutes):
            self.register_new_sky(update.serial_number, update)

        self._config["Weatherflow/daily_rain"] += update.accumulated_rain
        self._config["Weatherflow/hourly_rain"] += update.accumulated_rain

        self.update_sensor(update.serial_number, "lux", update.lux, autodisc.SensorDeviceClasses.ILLUMINANCE)
        self.update_sensor(update.serial_number, "uv_index", update.uv_index, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "accumulated_rain", update.accumulated_rain, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        try:
            if self._config.get("Weatherflow/wind_diff", None) is not None:
                diff = self._config["Weatherflow/wind_diff"]
                if update.wind_gust > (self._wind_filter["max"] + diff) or update.wind_gust < (self._wind_filter["max"] - diff):
                    self.update_sensor(update.serial_number, "wind_gust",
                        {"ms": update.wind_gust, "km/h": update.wind_gust * 3.6}
                        , autodisc.SensorDeviceClasses.GENERIC_SENSOR)
                    self._wind_filter["max"] = update.wind_gust
                        
                if update.wind_avg > (self._wind_filter["avg"] + diff) or update.wind_avg < (self._wind_filter["avg"] - diff):
                    self.update_sensor(update.serial_number, "wind_average", 
                        {"ms": update.wind_avg, "km/h": update.wind_avg * 3.6}
                        , autodisc.SensorDeviceClasses.GENERIC_SENSOR)
                    self._wind_filter["avg"] = update.wind_avg

                if update.wind_lull > (self._wind_filter["min"] + diff) or update.wind_lull < (self._wind_filter["min"] - diff):
                    self.update_sensor(update.serial_number, "wind_lull", 
                        {"ms": update.wind_lull, "km/h": update.wind_lull * 3.6}
                        , autodisc.SensorDeviceClasses.GENERIC_SENSOR)
                    self._wind_filter["min"] = update.wind_lull
            else:
                self.update_sensor(update.serial_number, "wind_gust",
                    {"ms": update.wind_gust, "km/h": update.wind_gust * 3.6}
                    , autodisc.SensorDeviceClasses.GENERIC_SENSOR)
                self.update_sensor(update.serial_number, "wind_average", 
                    {"ms": update.wind_avg, "km/h": update.wind_avg * 3.6}
                    , autodisc.SensorDeviceClasses.GENERIC_SENSOR)
                self.update_sensor(update.serial_number, "wind_lull", 
                    {"ms": update.wind_lull, "km/h": update.wind_lull * 3.6}
                    , autodisc.SensorDeviceClasses.GENERIC_SENSOR)

        except TypeError:
            pass
        self.update_sensor(update.serial_number, "wind_direction", update.wind_direction, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "solar_radiation", update.solar_radiation, autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_sensor(update.serial_number, "local_hour_rain_accumulation", self._config["Weatherflow/hourly_rain"], autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
        
        daily_rain_js = {
            "today": round(self._config["Weatherflow/daily_rain"], 1),
            "yesterday": round(self._config.get("Weatherflow/yesterday_daily_rain", 0), 1)
        }
        self.update_sensor(update.serial_number, "local_day_rain_accumulation", json.dumps(daily_rain_js), autodisc.SensorDeviceClasses.GENERIC_SENSOR)
        self.update_is_windy(update.serial_number, True, update.wind_avg, update.wind_direction)
	
        charging_str = "NULL"
        battery_str = 0
        sensors = ""
        
        if isinstance(update, ObsTempest.ObsTempest):
            last_pct = self._config.get("Weatherflow/{0}/last".format(update.serial_number), -1)
            if update.battery != last_pct:
                self._config["Weatherflow/{0}/last".format(update.serial_number)] = update.battery
            if last_pct == -1:
                last_pct = update.battery
            self._config["Weatherflow/{0}/last".format(update.serial_number)] = update.battery
            range_min = 1.8
            range_max = 2.85
            battery_str = math.floor(WeatherflowPlugin.percentageMinMax(update.battery, range_min, range_max))
            charging_str = "Lädt" if last_pct < update.battery else "Entlädt"
            if update.battery <= 2.355:
                charging_str = "Sensoren auf 5 Minuten intervall gesetzt, Blitzerkennung, Regen deaktiviert| {} Ultra Energiesparmodus".format(charging_str)
            elif update.battery <= 2.39:
                charging_str = "Windsensor auf 1 Minuten intervall gesetzt. | {} Energiesparmodus".format(charging_str)
            elif update.battery <= 2.415:
                charging_str =  "Windsensor auf 6 Sekunden intervall gesetzt. | {} Leichter Energiesparmodus".format(charging_str)
            else:
                charging_str = "OK | {} Kein Energiesparen".format(charging_str)
        else:
            charging_str = "on battery"
            battery_str = math.floor(WeatherflowPlugin.percentageMinMax(update.battery, 1.6, 3.18))

            if update.battery > 3.32:
                self._config["Weatherflow/sky_solar_module"] = True
            if self._config.get("Weatherflow/sky_solar_module", False):
                charging_str = "discharging"
                battery_str = round(WeatherflowPlugin.percentageMinMax(update.battery, 2.5, 3.6), 1)
                if update.battery > 3.2:
                    battery_str = 100
                    charging_str = "Komplett aufgeladen"
                elif update.battery > 3.5:
                    battery_str = 100
                    charging_str = "Aufladen"
                elif update.battery < 3.0:
                    charging_str = 'Unter "Working voltage"'
            elif update.battery < 1.8:
                charging_str = "Austauschen"
 
        if self._deviceUpdates[update.serial_number]._sensor_status == DeviceStatus.SensorStatus.OK:
            sensors = "OK"
        else:
            if self._deviceUpdates[update.serial_number]._sensor_status & DeviceStatus.SensorStatus.SKY_LIGHT_UV_FAILED:
                sensors = str(sensors) + "UV Sensor ist ausgefallen. "
            if self._deviceUpdates[update.serial_number]._sensor_status & DeviceStatus.SensorStatus.SKY_PRECIP_FAILED:
                sensors = str(sensors) + "Regen Sensor ist ausgefallen. "
            if self._deviceUpdates[update.serial_number]._sensor_status & DeviceStatus.SensorStatus.SKY_WIND_FAILED:
                sensors = str(sensors) + "Wind Sensor ist ausgefallen."

        if update.rain_type != 0:
            self._logger.info("rain_type: {}".format(update.rain_type))
            self.update_is_raining(update.serial_number, True, update.rain_type == 2)
    
        if self._config.get("Weatherflow/{0}/minBat".format(update.serial_number), 10) > update.battery:
            self._config["Weatherflow/{0}/minBat".format(update.serial_number)] = update.battery
        elif self._config.get("Weatherflow/{0}/maxBat".format(update.serial_number), 0) < update.battery:
            self._config["Weatherflow/{0}/maxBat".format(update.serial_number)] = update.battery
        
        rssi = -100
        try:
            rssi = self._deviceUpdates[update.serial_number]._rssi
        except:
            pass

        battery_json = {
                        "min": self._config.get("Weatherflow/{0}/minBat".format(update.serial_number), 0),
                        "max": self._config.get("Weatherflow/{0}/maxBat".format(update.serial_number), 0),
                        "now": battery_str,
                        "volt": update.battery,
                        "charging state": charging_str,
                        "rssi": rssi,
                        "sensors": sensors
                        }
        self.update_sensor(update.serial_number, "battery_sky", battery_json, autodisc.SensorDeviceClasses.BATTERY)


    def count_lightnings_per_minute(self):
        count = self._lightning_counter["count"]
        self._lightning_counter["count"] = 0
        if self._lightning_counter["init"] == 0 and self._lightning_counter["serial"] is not None:
            self._logger.info("Es Blitzt, Regestriere Blitze pro Minute zähler für {}".format(self._lightning_counter["serial"]))
            self._lightning_counter["init"] = 1
            self._lightning_counter["timer"] = threading.Timer(60, self.count_lightnings_per_minute)
            self._lightning_counter["timer"].start()
        if 0 < self._lightning_counter["init"] <= 10:
            if count == 0:
                self._lightning_counter["init"] += 1
            else:
                self._lightning_counter["init"] = 1
            self._lightning_counter["timer"] = threading.Timer(60, self.count_lightnings_per_minute)
            self._lightning_counter["timer"].start()
            self._logger.debug("Es blitzt immer nocht. Restarte timer...")
            self.update_sensor(self._lightning_counter["serial"], "es_blitzt", 1, autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
        elif self._lightning_counter["init"] > 5:
            self._lightning_counter["timer"] = None
            self._logger.debug("Es blitzt nicht mehr. Timer wird nicht neu gestartet...")
            self.update_sensor(self._lightning_counter["serial"], "es_blitzt", 0,autodisc.BinarySensorDeviceClasses.GENERIC_SENSOR)
            self._lightning_counter = {"count": 0, "timer": None, "serial": None, "init": 0, "lastTime": datetime.datetime.now()}

        if self._lightning_counter["serial"] is not None:
            self.update_sensor(self._lightning_counter["serial"], "lightning_count_min", count, autodisc.SensorDeviceClasses.GENERIC_SENSOR)

    def check_online_status(self):
        if self._timer is not None:
            self._timer.cancel()

        for serial in self._online_states.keys():
            last_update = self._online_states[serial]["lastUpdate"]
            timespan = datetime.datetime.now() - last_update
            if timespan.seconds > (self._online_states[serial]["intervall"] * 4) and self._online_states[serial]["wasOnline"]:
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

