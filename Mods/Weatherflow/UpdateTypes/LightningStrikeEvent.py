# -*- coding: utf-8 -*-
import datetime
import Mods.Weatherflow.UpdateTypes.updateType as ut


class LightningStrikeEvent:

    # {
    # 	  "type":"evt_strike",
    # 	  "device_id":1110,
    # 	  "evt":[1493322445,27,3848]
    # 	}

    @staticmethod
    def json_is_update_type(json: dict) -> bool:
        if json.get("type", None) == "evt_strike":
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
            obs = json["evt"]
            self.__timestamp = datetime.datetime.fromtimestamp(obs[0])
            self.__distance = obs[1]
            self.__energy = obs[2]
        except KeyError:
            self.__timestamp = datetime.datetime.now()
            self.__distance = -1
            self.__energy = -1

        self.__update_type = ut.UpdateType.LightningStrikeEvent

    @property
    def update_type(self) -> ut.UpdateType:
        return self.__update_type

    @property
    def timestamp(self):
        return self.__timestamp

    @property
    def distance(self):
        """ Entfernung zum Blitz in km """
        return self.__distance

    @property
    def energy(self):
        return self.__energy

    @property
    def serial_number(self) -> str:
        return self._serial_number
