# -*- coding: utf-8 -*-
import datetime
import Mods.Weatherflow.UpdateTypes.updateType as ut


class ObsAir:

    @staticmethod
    def json_is_update_type(json: dict) -> bool:
        if json.get("type", None) == "obs_air":
            return True
        return False

    def __init__(self, json):
        self._serial_number = json["serial_number"]
        self._hub_serial_number = json["hub_sn"]
        self._firmware_revision = json["firmware_revision"]

        obs = json["obs"][0]
        self.__timestamp = datetime.datetime.fromtimestamp(obs[0])
        self.__station_pressure = obs[1]
        self.__air_temperature = obs[2]
        self.__relative_humidity = obs[3]
        self._lightning_strike_count = obs[4]
        self._lightning_strike_avg_distance = obs[5]
        self._battery = obs[6]
        self._report_interval_minutes = obs[7]
        self.__update_type = ut.UpdateType.ObsAir

    @property
    def update_type(self) -> ut.UpdateType:
        return self.__update_type

    @property
    def serial_number(self) -> str:
        return self._serial_number

    @property
    def timestamp(self):
        return self.__timestamp

    @property
    def hub_serial(self):
        return self._hub_serial_number

    @property
    def firmware_revision(self) -> str:
        return self._firmware_revision

    @property
    def station_pressure(self):
        """ MB (millibar) """
        return self.__station_pressure

    @property
    def air_temperatur(self):
        """ °C Grad Celsius """
        return self.__air_temperature

    @property
    def relative_humidity(self):
        """ Relative Luftfeuchte """
        return self.__relative_humidity

    @property
    def lightning_strike_count(self):
        return self._lightning_strike_count

    @property
    def lightning_strike_avg_distance(self):
        """ Die durchschnittliche Distanz von Blitzen in km """
        return self._lightning_strike_avg_distance

    @property
    def battery(self):
        """ Das Ladelevel von der Batterie in Volt """
        return self._battery

    @property
    def report_intervall_minutes(self):
        """ Der intervall in Minuten, in dem neue Werte übertragen werden """
        return self._report_interval_minutes