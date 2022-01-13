# -*- coding: utf-8 -*-
import datetime
import Mods.Weatherflow.UpdateTypes.updateType as ut


class RapidWind:

    # {
    #  "type":"rapid_wind",
    #  "device_id":1110,
    #  "ob":[1493322445,2.3,128]
    # }

    @staticmethod
    def json_is_update_type(json: dict) -> bool:
        if json.get("type", None) == "rapid_wind":
            return True
        return False

    def __init__(self, json):
        try:
            self._serial_number = json["serial_number"]
        except KeyError:
            self._serial_number = "ERR_NOT_FOUND"

        try:
            self._hub_serial_number = json["hub_sn"]
        except KeyError:
            self._hub_serial_number = "ERR_NOT_FOUND"
        try:
            obs = json["ob"]
            self.__timestamp = datetime.datetime.fromtimestamp(obs[0])
            self.__wind_speed = obs[1]
            self.__wind_direction = obs[2]
        except KeyError:
            self.__timestamp = datetime.datetime.now()
            self.__wind_speed = 0
            self.__wind_direction = 0

        self.__update_type = ut.UpdateType.RapidWind

    @property
    def update_type(self) -> ut.UpdateType:
        return self.__update_type

    @property
    def timestamp(self):
        return self.__timestamp

    @property
    def wind_direction(self):
        """ Wind Richtung in Grad """
        return self.__wind_direction

    @property
    def wind_speed(self):
        """ Wind geschwindigkeit in m/s """
        return self.__wind_speed

    @property
    def serial_number(self) -> str:
        return self._serial_number

