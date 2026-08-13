# -*- coding: utf-8 -*-

from Mods.CoE.coe_lib import Datatypes
from Tools.Devices.Sensor import SensorDeviceClasses, StateClass

def getConfigKey() -> str:
    return "TA_CoE"

def get_sensor_class_from_mt(mt: Datatypes.MeasureType):
    match mt:
        case Datatypes.MeasureType.TEMPERATURE | Datatypes.MeasureType.CELSIUS | Datatypes.MeasureType.KELVIN:
            return  SensorDeviceClasses.TEMPERATURE
        case Datatypes.MeasureType.SECONDS | Datatypes.MeasureType.MINUTES | Datatypes.MeasureType.DAYS | Datatypes.MeasureType.HOURS:
            return  SensorDeviceClasses.DURATION
        case Datatypes.MeasureType.KILOWATT:
            return  SensorDeviceClasses.POWER
        case Datatypes.MeasureType.KILOWATTHOURS | Datatypes.MeasureType.MEGAWATTHOURS:
            return  SensorDeviceClasses.ENERGY
        case Datatypes.MeasureType.VOLT:
            return  SensorDeviceClasses.VOLTAGE
        case Datatypes.MeasureType.MILLIAMPERE:
            return  SensorDeviceClasses.CURRENT
        case Datatypes.MeasureType.LITER:
            return  SensorDeviceClasses.WATER
        case Datatypes.MeasureType.Hz:
            return  SensorDeviceClasses.FREQU
        case Datatypes.MeasureType.BAR:
            return  SensorDeviceClasses.PRESSURE
        case Datatypes.MeasureType.KILLOMETER | Datatypes.MeasureType.METER | Datatypes.MeasureType.MILLIMETER:
            return  SensorDeviceClasses.DISTANCE
        case Datatypes.MeasureType.KUBIKMETER:
            return  SensorDeviceClasses.VOL
        case Datatypes.MeasureType.KMH | Datatypes.MeasureType.METERSECOND:
            return  SensorDeviceClasses.SPEED
        case Datatypes.MeasureType.MILLIMETER_DAY | Datatypes.MeasureType.MILLIMETER_HOUR:
            return  SensorDeviceClasses.PRECIPITATION_INTENS
        case Datatypes.MeasureType.MILLIMETER:
            return  SensorDeviceClasses.PRECIPATION
        case Datatypes.MeasureType.EUR | Datatypes.MeasureType.USD:
            return  SensorDeviceClasses.MONETARY
        case _:
            return  SensorDeviceClasses.GENERIC_SENSOR

def get_sensor_state_class_from_mt(mt: Datatypes.MeasureType):
    match mt:
        case Datatypes.MeasureType.TEMPERATURE | Datatypes.MeasureType.CELSIUS | Datatypes.MeasureType.KELVIN:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.SECONDS | Datatypes.MeasureType.MINUTES | Datatypes.MeasureType.DAYS | Datatypes.MeasureType.HOURS:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.KILOWATT:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.KILOWATTHOURS | Datatypes.MeasureType.MEGAWATTHOURS:
            return  StateClass.TOTAL_INCREASING
        case Datatypes.MeasureType.VOLT:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.MILLIAMPERE:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.LITER:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.Hz:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.BAR:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.KILLOMETER | Datatypes.MeasureType.METER | Datatypes.MeasureType.MILLIMETER:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.KUBIKMETER:
            return  StateClass.TOTAL_INCREASING
        case Datatypes.MeasureType.KMH | Datatypes.MeasureType.METERSECOND:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.MILLIMETER_DAY | Datatypes.MeasureType.MILLIMETER_HOUR:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.MILLIMETER:
            return  StateClass.MEASUREMENT
        case Datatypes.MeasureType.EUR | Datatypes.MeasureType.USD:
            return  StateClass.MEASUREMENT
        case _:
            return  StateClass.NONE