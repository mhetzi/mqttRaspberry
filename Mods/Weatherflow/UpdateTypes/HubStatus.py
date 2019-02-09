# -*- coding: utf-8 -*-
import datetime
import Mods.Weatherflow.UpdateTypes.updateType as ut


class HubStatus:

    @staticmethod
    def json_is_update_type(json: dict) -> bool:
        if json.get("type", None) == "hub_status":
            return True
        return False

    def __init__(self, json):
        self._serial_number = json["serial_number"]
        self._firmware_revision = json["firmware_revision"]
        self._uptime = json["uptime"]
        self._timestamp = datetime.datetime.fromtimestamp(json["timestamp"])
        self._rssi = json["rssi"]
        self._seq = json["seq"]
        self.__update_type = ut.UpdateType.HubStatus

    @property
    def update_type(self) -> ut.UpdateType:
        return self.__update_type

    @property
    def serial_number(self) -> str:
        return self._serial_number

    @property
    def firmware_revision(self) -> str:
        return self._firmware_revision

    @property
    def uptime(self) -> int:
        # Die Zeit in Sekunden seit dem letzten Start
        return self._uptime

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def rssi(self):
        return self._rssi

    @property
    def seq(self):
        return self._seq