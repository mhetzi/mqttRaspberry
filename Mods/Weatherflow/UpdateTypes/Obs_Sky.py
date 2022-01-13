# -*- coding: utf-8 -*-
import datetime
import Mods.Weatherflow.UpdateTypes.updateType as ut


class ObsSky:

    @staticmethod
    def json_is_update_type(json: dict) -> bool:
        if json.get("type", None) == "obs_sky":
            return True
        return False

    def __init__(self, json):
        self._serial_number = json["serial_number"]
        self._hub_serial_number = json["hub_sn"]
        self._firmware_revision = json["firmware_revision"]
        obs = json["obs"][0]

        self.__timestamp = datetime.datetime.fromtimestamp(obs[0])
        self.__lux = obs[1]
        self.__uv_index = obs[2]
        self.__accumulated_rain_mm = obs[3] if isinstance(obs[3], (int, float, complex)) else 0
        self.__wind_lull = obs[4]
        self.__wind_avg = obs[5]
        self.__wind_gust = obs[6]
        self.__wind_direction = obs[7] if isinstance(obs[7], (int, float, complex)) else 0
        self.__battery = obs[8]
        self.__report_interval_minutes = obs[9]
        self.__solar_radiation = obs[10]
        self.__local_day_rain_accumulation = obs[11] if isinstance(obs[11], (int, float, complex)) else 0
        self.__rain_type = obs[12]
        self.__wind_sampling_rate = obs[13]
        self.__update_type = ut.UpdateType.ObsSky

    @property
    def update_type(self) -> ut.UpdateType:
        return self.__update_type

    @property
    def firmware_revision(self) -> str:
        return self._firmware_revision

    @property
    def timestamp(self):
        return self.__timestamp

    @property
    def serial_number(self) -> str:
        return self._serial_number

    @property
    def hub_serial(self):
        return self._serial_number

    @property
    def battery(self):
        """ Das Ladelevel von der Batterie in Volt """
        return self.__battery

    @property
    def report_interval_minutes(self):
        """ Der interval in Minuten, in dem neue Werte übertragen werden """
        return self.__report_interval_minutes

    @property
    def report_intervall_minutes(self): # Kompatibilität mir ObsTempest
        """ Der interval in Minuten, in dem neue Werte übertragen werden """
        return self.__report_interval_minutes

    @property
    def lux(self):
        """ Illuminance	Lux """
        return self.__lux

    @property
    def uv_index(self):
        """ UV Index """
        return self.__uv_index

    @property
    def accumulated_rain(self):
        """ Niederschlag in mm """
        return self.__accumulated_rain_mm

    @property
    def wind_lull(self):
        """ Wind (m/s) minimalwert der letzten 3 Messungen """
        return self.__wind_lull

    @property
    def wind_avg(self):
        """ Wind (m/s) Mittelwer über den Zeitraum von report_interval_minutes() """
        return self.__wind_avg

    @property
    def wind_gust(self):
        """ Wind (m/s) maximalwert der letzten 3 Messungen """
        return self.__wind_gust

    @property
    def wind_direction(self):
        """ Wind Richtung in Grad """
        return self.__wind_direction

    @property
    def solar_radiation(self):
        """ Sonnen Strahlung in Watt pro m² """
        return self.__solar_radiation

    @property
    def local_day_rain_accumulation(self):
        """ Lokaler Tages Regen Niederschlag im mm """
        return self.__local_day_rain_accumulation

    @property
    def rain_type(self):
        """Welche art von Regen (None, Regen, Hagel)"""
        return self.__rain_type
