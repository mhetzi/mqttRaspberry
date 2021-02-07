# -*- coding: utf-8 -*-

from Tools.Devices.BinarySensor import BinarySensor
from Tools.Devices.Sensor import Sensor
from Tools.PluginManager import PluginManager
import Tools.Autodiscovery as Autodiscovery
from Tools.Devices.Filters.DeltaFilter import DeltaFilter

from logging import Logger
import json

import Mods.victron.Constants as CONST
from Mods.victron.vcSerial import Connection

class MPPT(CONST.VEDirectDevice):
    _callbacks = {}

    def __init__(self, logger: Logger, pman: PluginManager, serial: Connection) -> None:
        super().__init__()
        self._log = logger.getChild("MPPT")
        self._pman = pman
        self._vcserial = serial

        self.battery_voltage = Sensor(
            self._log, self._pman, "Batterie V",
            Autodiscovery.SensorDeviceClasses.VOLTAGE, measurement_unit="V", device=self._vcserial._device,
            value_template="{{value_json.v}}", json_attributes=True
        )
        self.battery_voltage.addFilter( DeltaFilter(0.03) )

        self.battery_current = Sensor(
            self._log, self._pman, "Batterie (A)",
            Autodiscovery.SensorDeviceClasses.CURRENT, measurement_unit="A", device=self._vcserial._device,
            value_template="{{value_json.a}}", json_attributes=True
        )

        self.panel_voltage = Sensor(
            self._log, self._pman, "Panel (V)",
            Autodiscovery.SensorDeviceClasses.VOLTAGE, measurement_unit="V", device=self._vcserial._device,
            value_template="{{value_json.v}}", json_attributes=True
        )
        self.panel_voltage.addFilter( DeltaFilter(1) )

        self.panel_power = Sensor(
            self._log, self._pman, "Panel (W)",
            Autodiscovery.SensorDeviceClasses.POWER, measurement_unit="W", device=self._vcserial._device,
            value_template="{{value_json.w}}", json_attributes=True
        )
        self.panel_power.addFilter( DeltaFilter(1) )

        self.load = Sensor(
            self._log, self._pman, "Last",
            Autodiscovery.SensorDeviceClasses.CURRENT, measurement_unit="A", device=self._vcserial._device,
            value_template="{{value_json.a}}", json_attributes=True
        )
        self.load_enabled = BinarySensor(
            self._log, self._pman, "Last",
            Autodiscovery.BinarySensorDeviceClasses.POWER, device=self._vcserial._device
        )

        self.yield_total = Sensor(
            self._log, self._pman, "Gesammelt (total)",
            Autodiscovery.SensorDeviceClasses.ENERGY, measurement_unit="kWh", device=self._vcserial._device,
            value_template="{{value_json.kWh}}", json_attributes=True
        )
        self.yield_today = Sensor(
            self._log, self._pman, "Gesammelt (Heute)",
            Autodiscovery.SensorDeviceClasses.ENERGY, measurement_unit="kWh", device=self._vcserial._device,
            value_template="{{value_json.kWh}}", json_attributes=True
        )
        self.yield_yesterday = Sensor(
            self._log, self._pman, "Gesammelt (Gestern)",
            Autodiscovery.SensorDeviceClasses.ENERGY, measurement_unit="kWh", device=self._vcserial._device,
            value_template="{{value_json.kWh}}", json_attributes=True
        )

        
        self.max_power_today = Sensor(
            self._log, self._pman, "Maximal Strom (Heute)",
            Autodiscovery.SensorDeviceClasses.POWER, measurement_unit="W", device=self._vcserial._device,
            value_template="{{value_json.w}}", json_attributes=True
        )
        self.max_power_yesterday = Sensor(
            self._log, self._pman, "Maximal Strom (Gestern)",
            Autodiscovery.SensorDeviceClasses.POWER, measurement_unit="W", device=self._vcserial._device,
            value_template="{{value_json.w}}", json_attributes=True
        )

        self.error = BinarySensor(
            self._log, self._pman, "Fehler",
            Autodiscovery.BinarySensorDeviceClasses.PROBLEM, "", device=self._vcserial._device,
            value_template="{{value_json.is_error}}", json_attributes=True
        )
        self.state_of_operation = Sensor(
            self._log, self._pman, "Status",
            Autodiscovery.SensorDeviceClasses.GENERIC_SENSOR, "", device=self._vcserial._device
        )
        self.mppt = Sensor(
            self._log, self._pman, "MPPT",
            Autodiscovery.SensorDeviceClasses.GENERIC_SENSOR, "", device=self._vcserial._device
        )

    def register_entities(self):
        self.battery_current.register()
        self.battery_voltage.register()
        self.error.register()
        self.load.register()
        self.load_enabled.register()
        self.max_power_today.register()
        self.max_power_yesterday.register()
        self.panel_power.register()
        self.panel_voltage.register()
        self.state_of_operation.register()
        self.yield_today.register()
        self.yield_total.register()
        self.yield_yesterday.register()
        self.mppt.register()
        
        self._callbacks["V"]    = self.update_battery_voltage
        self._callbacks["VPV"]  = self.update_panel_voltage
        self._callbacks["PPV"]  = self.update_panel_power
        self._callbacks["I"]    = self.update_battery_current
        self._callbacks["IL"]   = self.update_load_current
        self._callbacks["LOAD"] = self.update_load_state
        self._callbacks["H19"]  = self.update_yield_total
        self._callbacks["H20"]  = self.update_yield_today
        self._callbacks["H21"]  = self.update_max_power_today
        self._callbacks["H22"]  = self.update_yield_yesterday
        self._callbacks["H23"]  = self.update_max_power_yesterday
        self._callbacks["ERR"]  = self.update_ERROR
        self._callbacks["CS"]   = self.update_state_operation
        self._callbacks["MPPT"] = self.update_mppt

        self._vcserial.set_callbacks(self._callbacks)

    def update_battery_voltage(self, mV: str):
        mV = int(mV)
        js = {"v": mV / 1000}
        self.battery_voltage(js, mainState=mV / 1000)
    
    def update_panel_voltage(self, mV: str):
        mV = int(mV)
        js = {"v": mV / 1000}
        self.panel_voltage(js, mainState=mV / 1000)
    
    def update_panel_power(self, w: str):
        w = int(w)
        js = {"w": w}
        self.panel_power(js, mainState=w)

    def update_battery_current(self, mA:str):
        mA = int(mA)
        js = {"a": mA / 1000}
        self.battery_current(json.dumps(js))
    
    def update_load_current(self, mA: str):
        mA = int(mA)
        js = {"a": mA / 1000}
        self.load(json.dumps(js))

    def update_load_state(self, on:str):
        self.load_enabled.turnOnOff( on == "ON" )

    def update_yield_total(self, kWh: str):
        kWh = float(kWh)
        js = {"kWh": kWh * 0.01}
        self.yield_total(json.dumps(js))
    
    def update_yield_today(self, kWh: str):
        kWh = float(kWh)
        js = {"kWh": kWh * 0.01}
        self.yield_today(json.dumps(js))
    
    def update_max_power_today(self, w: str):
        w = int(w)
        js = {"w": w}
        self.max_power_today(json.dumps(js))

    def update_yield_yesterday(self, kWh: str):
        kWh = float(kWh)
        js = {"kWh": kWh * 0.01}
        self.yield_yesterday(json.dumps(js))

    def update_max_power_yesterday(self, w: str):
        w = int(w)
        js = {"w": w}
        self.max_power_yesterday(json.dumps(js))

    def update_ERROR(self, err: str):
        err = int(err)
        err_str = CONST.ERR[err]
        
        js = {
            "is_error": 0 if err_str == CONST.ERR[0] else 1,
            "Errno": err,
            "Fehler": err_str
        }
        self.error.turn(js)
    
    def update_state_operation(self, state: str):
        state = int(state)
        self.state_of_operation(CONST.CS.get(state, "Unbekannt"))

    def update_mppt(self, state: str):
        if state == "0":
            self.mppt("AUS")
        elif state == "1":
            self.mppt("Voltage or Current limited")
        elif state == "2":
            self.mppt("MPPT Tracker active")