# -*- coding: utf-8 -*-
import datetime
import enum
import Mods.Weatherflow.UpdateTypes.updateType as ut


class SensorStatus(enum.IntEnum):
    OK = int(0x00000000)
    AIR_LIGHTNING_FAILED = int(0x00000001)
    AIR_LIGHTNING_NOISE = int(0x00000002)
    AIR_LIGHTNING_DISTURBER = int(0x00000004)
    AIR_PRESSURE_FAILED = int(0x00000008)
    AIR_TEMPERATURE_FAILED = int(0x00000010)
    AIR_RH_FAILED = int(0x00000020)
    SKY_WIND_FAILED = int(0x00000040)
    SKY_PRECIP_FAILED = int(0x00000080)
    SKY_LIGHT_UV_FAILED = int(0x00000100)


class DeviceStatus:

    @staticmethod
    def json_is_update_type(json: dict) -> bool:
        if json.get("type", None) == "device_status":
            return True
        return False

    def __init__(self, json):
        self._serial_number = json["serial_number"]
        self._hub_serial_number = json["hub_sn"]
        self._uptime = json["uptime"]
        self._timestamp = datetime.datetime.fromtimestamp(json["timestamp"])
        self._voltage = json["voltage"]
        self._firmware_revision = json["firmware_revision"]
        self._rssi = json["rssi"]
        self._sensor_status = json["sensor_status"]
        self.__update_type = ut.UpdateType.DeviceStatus

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
    def hub_serial(self):
        return self._serial_number

    @property
    def rssi(self):
        return self._rssi

    @property
    def voltage(self):
        return self._voltage

    @property
    def sensor_status(self) -> SensorStatus:
        return self._sensor_status
