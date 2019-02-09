# -*- coding: utf-8 -*-
import datetime
import Mods.Weatherflow.UpdateTypes.updateType as ut


class RainStartEvent:

    @staticmethod
    def json_is_update_type(json: dict) -> bool:
        if json.get("type", None) == "evt_precip":
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
            obs = json["obs"]
            self.__timestamp = datetime.datetime.fromtimestamp(obs[0])
        except KeyError:
            self.__timestamp = datetime.datetime.now()
        self.__update_type = ut.UpdateType.RainStart

    @property
    def update_type(self) -> ut.UpdateType:
        return self.__update_type

    @property
    def timestamp(self):
        return self.__timestamp

    @property
    def serial_number(self) -> str:
        return self._serial_number
