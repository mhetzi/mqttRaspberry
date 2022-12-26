# -*- coding: utf-8 -*-

import enum
from typing import Union
try:
    import json
except ImportError:
    import simplejson as json
import logging

try:
    import paho.mqtt.client as mclient
except ImportError as ie:
    from Tools import error as err
    try:
        err.try_install_package('paho.mqtt', throw=ie, ask=False)
    except err.RestartError:
        import paho.mqtt.client as mclient

class Component(enum.Enum):
    BINARY_SENROR = "binary_sensor"
    COVER   = "cover"
    FAN     = "fan"
    LIGHT   = "light"
    SWITCH  = "switch"
    SENSOR  = "sensor"
    LOCK    = "lock"
    CLIMATE = "climate"
    NUMBER  = "number"

class DeviceClass:
    pass

class SensorDeviceClasses(DeviceClass, enum.Enum):
    BATTERY = "battery" # Percentage
    HUMIDITY = "humidity"
    ILLUMINANCE = "illuminance"
    TEMPERATURE = "temperature"
    POWER = "power" # W or kW
    SIGNAL_STRENGTH = "signal_strength" #dB dBm
    PRESSURE = "pressure" #hPa mbar
    TIMESTAMP = "timestamp" #ISO 8601

    CURRENT = "current" # Current in Ampere (A)
    ENERGY = "energy" # Energy in Wh oder kWh
    POWER_FACTOR = "power_factor" # in percentage
    VOLTAGE = "voltage"

    VA = "apparent_power" # Apparent power in VA.
    AQI = "aqi" # Air Quality Index
    CO2 = "carbon_dioxide" # Carbon Dioxide in CO2 (Smoke)
    CO = "carbon_monoxide" # Carbon Monoxide in CO (Gas CNG/LPG)
    DATE = "date" # Date string (ISO 8601)
    DISTANCE = "distance" # Generic distance in km, m, cm, mm, mi, yd, or in
    DURATION = "duration" # Duration in days, hours, minutes or seconds
    FREQU = "frequency" # Frequency in Hz, kHz, MHz or GHz
    GAS = "gas" # Gasvolume in m³ or ft³
    MOISTURE = "moisture" # Percentage of water in a substance
    MONETARY = "monetary" # The monetary value
    NITROGEN_DIOXIDE = "nitrogen_dioxide" # Concentration of Nitrogen Dioxide in µg/m³
    NITROGEN_MONOXIDE = "nitrogen_monoxide" # Concentration of Nitrogen Monoxide in µg/m³
    NITROUS_OXIDE = "nitrous_oxide" # Concentration of Nitrous Oxide in µg/m³
    OZONE = "ozone" # Concentration of Ozone in µg/m³
    PM1 = "pm1" # Concentration of particulate matter less than 1 micrometer in µg/m³
    PM1_0 = "pm10" # Concentration of particulate matter less than 10 micrometers in µg/m³
    PM2_5 = "pm25" # Concentration of particulate matter less than 2.5 micrometers in µg/m³
    PRECIPATION = "precipitation" # Accumulated precipitation in in or mm
    PRECIPITATION_INTENS = "precipitation_intensity" # Precipitation intensity in in/d, in/h, mm/d, or mm/h
    REACTIVE_PWR = "reactive_power" # Reactive power in var
    SPEED = "speed" # Generic speed in ft/s, in/d, in/h, km/h, kn, m/s, mph, or mm/d
    SUPLPGUR_DIOXIDE = "sulphur_dioxide" # Concentration of sulphur dioxide in µg/m³
    VOC = "volatile_organic_compounds" # Concentration of volatile organic compounds in µg/m³
    VOL = "volume" # Generic volume in L, mL, gal, fl. oz., m³, or ft³
    WATER = "water" # Water consumption in L, gal, m³, or ft³
    WEIGHT = "weight" # Generic mass in kg, g, mg, µg, oz, or lb
    WIND_SPEED = "wind_speed" # Wind speed in ft/s, km/h, kn, m/s, or mph

    GENERIC_SENSOR = None


class BinarySensorDeviceClasses(DeviceClass, enum.Enum):
    BATTERY = "battery"
    BATTERY_CHARGING = "battery_charging"
    COLD = "cold"
    CONNECTIVITY = "connectivity"
    DOOR = "door"
    GARAGE_DOOR = "garage_door"
    GAS = "gas"
    HEAT = "heat"
    LIGHT = "light"
    LOCK = "lock"
    MOISTURE = "moisture"
    MOTION = "motion"
    MOVING = "moving"
    OCCUPANCY = "occupancy"
    OPENING = "opening"
    PLUG = "plug"
    POWER = "power"
    PRESENCE = "presence"
    PROBLEM = "problem"
    SAFETY = "safety"
    SMOKE = "smoke"
    SOUND = "sound"
    VIBRATION = "vibration"
    WINDOW = "window"
    GENERIC_SENSOR = None

class CoverDeviceClasses(DeviceClass, enum.Enum):
    AWNING = "awning"
    BLINDS = "blind"
    CURTAIN = "curtain"
    DAMPER = "damper"
    DOOR = "door"
    GARAGE = "garage"
    GATE = "gate"
    SHADE = "shade"
    SHUTTER = "shutter"
    WINDOW = "window"
    GENERIC_SENSOR = None

class LightOnCommandType(enum.Enum):
    LAST = "last"
    FIRTS = "first"

class DeviceInfo:
    IDs = []
    pi_serial = ""
    mfr = ""
    model = ""
    name  = ""
    sw_version = ""
    via_device = None

__global_device_info = None

class Topics:
    state = ""
    command = ""
    config = ""
    ava_topic: Union[str, None] = ""
    base = ""

    @staticmethod
    def set_standard_deviceinfo(di: DeviceInfo):
        global __global_device_info
        __global_device_info = di
    
    @staticmethod
    def get_std_devInf() -> DeviceInfo:
        global __global_device_info
        return __global_device_info

    def __init__(self, comp: Component, dev_class: DeviceClass, autodiscovery: bool):
        self._component = comp
        if isinstance(dev_class, BinarySensorDeviceClasses) or isinstance(dev_class, SensorDeviceClasses) or isinstance(dev_class, CoverDeviceClasses):
            self._dev_class = dev_class
        else:
            self._dev_class = SensorDeviceClasses.GENERIC_SENSOR
        
        if comp == Component.LIGHT:
            self.brightness_cmd = None
            self.brightness_state = None
            self.color_temp_cmd = None
            self.color_temp_state = None
            self.effect_cmd = None
            self.effect_state = None
            self.hs_cmd = None
            self.hs_state = None
            self.white_cmd = None
            self.white_state = None
            self.rgb_cmd = None
            self.rgb_state = None
            self.xy_cmd = None
            self.xy_state = None

    def register(self, mqtt_client:mclient.Client, name: str, measurement_unit: str, ava_topic=None, value_template=None, json_attributes=False, device=None, unique_id=None, icon=None, asDict=False):
        config = self.get_config_payload(
            name=name,
            measurement_unit=measurement_unit,
            ava_topic=ava_topic,
            value_template=value_template,
            json_attributes=json_attributes,
            device=device,
            unique_id=unique_id,
            icon=icon,
            asDict=asDict
        )
        mqtt_client.publish(self.config, config, 0, True)
    
    def register_light(self, mqtt_client:mclient.Client, name:str, unique_id=None, device=None, brightness_scale=0, color_temp=False, effect_list=[], hs=False, json_attributes=False, min_mireds=None, max_mireds=None,max_white_value=0,rgb=False,xy=False, on_command_type=LightOnCommandType.LAST):
        config = self.get_light_config_payload(
            name=name,
            unique_id=unique_id,
            device=device,
            brightness_scale=brightness_scale,
            color_temp=color_temp,
            effect_list=effect_list,
            hs=hs,
            json_attributes=json_attributes,
            min_mireds=min_mireds, max_mireds=max_mireds,
            max_white_value=max_white_value,
            rgb=rgb, xy=xy,on_command_type=on_command_type
        )
        mqtt_client.publish(self.config, config, 0, True)

    # Wenn unique_id gesetzt ist wird die globale device info verwendet, ist device gesetzt wird diese device info genommen
    def get_config_payload(self, name: str, measurement_unit: str, ava_topic=None, value_template=None, json_attributes=False, device=None, unique_id=None, icon=None, asDict=False, append_data=None, keep_light_attribs=False) -> str:
        
        p = append_data if isinstance(append_data, dict) else {}

        p["name"] = name

        if self._component != Component.CLIMATE:
            p["state_topic"] = self.state

        if self._component == Component.COVER:
            p["position_topic"] = self.state
            del p["state_topic"]
            p["set_position_topic"] = self.command

        if self._component == Component.SENSOR and not isinstance(self._dev_class, BinarySensorDeviceClasses):
            p["unit_of_measurement"] = measurement_unit
        
        if self._component == Component.COVER and value_template is not None:
            p["position_template"] = value_template
            value_template = None

        if isinstance(self._dev_class, BinarySensorDeviceClasses):
            p["payload_on"]  = 1
            p["payload_off"] = 0
        
        if icon is not None:
            p["icon"] = icon

        try:
            if self._dev_class.value is not None:
                p["device_class"] = str(self._dev_class.value)
                logging.getLogger("Launch").getChild("autodisc").debug("Config Payload {} wird DeviceClass {} angehängt.".format(name, str(self._dev_class.value)))
        except:
            logging.getLogger("Launch").getChild("autodisc").warning("ConfigPayload ({}) anhängen fehlgeschlagen.".format(str))
            del p["device_class"]

        if "device_class" in p.keys() and p["device_class"] is None:
            logging.getLogger("Launch").getChild("autodisc").debug("del[\"device_class\"]")
            del p["device_class"]

        if self.ava_topic is not None:
            ava_topic = self.ava_topic
        if ava_topic is not None:
            p["availability_topic"] = ava_topic
        
        if self._component != Component.SENSOR and self._component != Component.BINARY_SENROR:
            logging.getLogger("Launch").getChild("autodisc").debug("Command_topic [{}] wird gebraucht".format(self.command))
            p["command_topic"] = self.command
        else:
            logging.getLogger("Launch").getChild("autodisc").debug("Command_topic [{}] wird nicht gebraucht".format(self.command))
        if value_template is not None:
            p["value_template"] = value_template
        if json_attributes is True:
            p["json_attributes_topic"] = self.state

        if device is None and isinstance(__global_device_info, DeviceInfo) and unique_id is not None:
            device = __global_device_info

        if (device is not None and isinstance(device, DeviceInfo) and unique_id is not None):
            p["device"] = {
                "identifiers": device.IDs,
                "manufacturer": device.mfr,
                "model": device.model,
                "name": device.name,
                "sw_version": device.sw_version,
            }
            if device.via_device is not None:
                p["device"]["via_device"] = device.via_device
        elif device is not None and unique_id is None:
            raise AttributeError("Wenn Device verwendet wird muss auch unique_id gesetzt werden.")

        if unique_id is not None:
            p["unique_id"] = unique_id.replace(" ", "_").replace("-","_")
        if asDict:
            return p
        try:
            return json.dumps(p)
        except Exception:
            logging.getLogger("Launch").getChild("autodisc").info("JSON Dumping hat fehler verursacht. Object:{}", p)

    def get_light_config_payload(self, name:str, unique_id=None, device=None, brightness_scale=0, color_temp=False, effect_list=[], hs=False, json_attributes=False, min_mireds=None, max_mireds=None,max_white_value=0,rgb=False,xy=False, on_command_type=LightOnCommandType.LAST):

        data = {}
        if brightness_scale is not None and brightness_scale > 0:
            data["brightness_scale"] = brightness_scale
            self.brightness_cmd = "{}/brightness".format(self.command)
            self.brightness_state = "{}/brightness".format(self.state)
            data["brightness_command_topic"] = self.brightness_cmd
            data["brightness_state_topic"] = self.brightness_state

        if color_temp:
            self.color_temp_cmd = "{}/ct".format(self.command)
            self.color_temp_state = "{}/ct".format(self.state)
            data["color_temp_command_topic"] = self.color_temp_cmd
            data["color_temp_state_topic"] = self.color_temp_state
        
        data["command_topic"] = self.command

        if len(effect_list) > 0:
            self.effect_cmd   = "{}/effect".format(self.command)
            self.effect_state = "{}/effect".format(self.state)
            data["effect_command_topic"] = self.effect_cmd
            data["effect_state_topic"] = self.effect_state
            data["effect_list"] = effect_list
        
        if hs:
            self.hs_cmd = "{}/hs".format(self.command)
            self.hs_state = "{}/hs".format(self.state)
            data["hs_command_topic"] = self.hs_cmd
            data["hs_state_topic"]   = self.hs_state

        if min_mireds is not None and max_mireds is not None and  min_mireds > 0 and max_mireds > 0:
            data["max_mireds"] = max_mireds
            data["min_mireds"] = min_mireds
        
        data["on_command_type"] = on_command_type.value

        if rgb:
            self.rgb_cmd   = "{}/rgb".format(self.command)
            self.rgb_state = "{}/rgb".format(self.state)
            data["rgb_command_topic"] = self.rgb_cmd
            data["rgb_state_topic"] = self.rgb_state
        
        data["state_topic"] = self.state

        if max_white_value is not None and max_white_value > 0:
            self.white_cmd   = "{}/white".format(self.command)
            self.white_state = "{}/white".format(self.state)
            data["white_value_command_topic"] = self.white_cmd
            data["white_value_state_topic"]   = self.white_state
            data["white_value_scale"] = max_white_value

        if xy:
            self.hs_cmd   = "{}/xy".format(self.command)
            self.hs_state = "{}/xy".format(self.state)
            data["xy_command_topic"] = self.xy_cmd
            data["xy_state_topic"]   = self.xy_state

        return self.get_config_payload(
            name=name,
            json_attributes=json_attributes,
            unique_id=unique_id,
            device=device,
            append_data=data,
            keep_light_attribs=True,
            measurement_unit=None
        )


def getTopics(discoveryPrefix: str, comp: Component, devicedID: str, entitiyID: str, device_class: DeviceClass) -> Topics:

    if comp == Component.SENSOR and isinstance(device_class, BinarySensorDeviceClasses):
        print("getTopics: BinarySensorDeviceClasses angegeben, Component ist aber Sensor, Sensor wird zu BinarySensor abgeändert.")
        comp = Component.BINARY_SENROR

    
    import re
    safename = re.sub('[\W_]+', '', entitiyID) 

    if discoveryPrefix is not None:
        mainPath = "{0}/{1}/{2}/{3}/".format(discoveryPrefix, str(comp.value), devicedID, safename).replace(" ", "_").replace("-","_")
    else:
        mainPath = "{0}/{1}/{2}/".format(devicedID, comp.value, safename).replace(" ", "_").replace("-","_")
    t = Topics(comp, device_class, discoveryPrefix is not None)
    t.state = mainPath + "state"
    t.command = mainPath + "set"
    t.config = mainPath + "config" if discoveryPrefix is not None else None
    t.ava_topic = mainPath + "online"
    t.base = mainPath
    return t
