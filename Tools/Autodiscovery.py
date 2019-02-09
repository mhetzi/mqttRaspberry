# -*- coding: utf-8 -*-

import enum
try:
    import json
except ImportError:
    import simplejson as json
import logging

class Component(enum.Enum):
    BINARY_SENROR = "binary_sensor"
    COVER = "cover"
    FAN = "fan"
    LIGHT = "light"
    SWITCH = "switch"
    SENSOR = "sensor"


class DeviceClass:
    pass


class SensorDeviceClasses(DeviceClass, enum.Enum):
    BATTERY = "battery"
    HUMIDITY = "humidity"
    ILLUMINANCE = "illuminance"
    TEMPERATURE = "temperature"
    GENERIC_SENSOR = None


class BinarySensorDeviceClasses(DeviceClass, enum.Enum):
    BATTERY = "battery"
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
    WINDOW = "window"
    GARAGE = "garage"
    GENERIC_SENSOR = None

class DeviceInfo:
    IDs = []
    mfr = ""
    model = ""
    name  = ""
    sw_version = ""

class Topics:
    state = ""
    command = ""
    config = ""
    ava_topic = ""

    def __init__(self, comp: Component, dev_class: DeviceClass, autodiscovery: bool):
        self._component = comp
        if isinstance(dev_class, BinarySensorDeviceClasses) or isinstance(dev_class, SensorDeviceClasses) or isinstance(dev_class, CoverDeviceClasses):
            self._dev_class = dev_class
        else:
            self._dev_class = SensorDeviceClasses.GENERIC_SENSOR

    def get_config_payload(self, name: str, measurement_unit: str, ava_topic=None, value_template=None, json_attributes=None, device=None, unique_id=None) -> str:

        p = {
            "name": name,
            "state_topic": self.state
        }

        if self._component == Component.SENSOR and not isinstance(self._dev_class, BinarySensorDeviceClasses):
            p["unit_of_measurement"] = measurement_unit

        if isinstance(self._dev_class, BinarySensorDeviceClasses):
            p["payload_on"]  = 1
            p["payload_off"] = 0

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

        if ava_topic is not None:
            p["availability_topic"] = ava_topic
        if self._component != Component.SENSOR and self._component != Component.BINARY_SENROR:
            p["command_topic"] = self.command
        if value_template is not None:
            p["value_template"] = value_template
        if json_attributes is True:
            p["json_attributes_topic"] = self.state

        if (device is not None and isinstance(device, DeviceInfo) and unique_id is not None):
            p["device"] = {
                "identifiers": device.IDs,
                "manufacturer": device.mfr,
                "model": device.model,
                "model": device.name,
                "sw_version": device.sw_version
            }
        elif device is not None and unique_id is None:
            raise AttributeError("Wenn Device verwendet wird muss auch unique_id gesetzt werden.")

        if unique_id is not None:
            p["unique_id"] = unique_id

        try:
            return json.dumps(p)
        except Exception:
            logging.getLogger("Launch").getChild("autodisc").info("JSON Dumping hat fehler verursacht. Object:{}", p)


def getTopics(discoveryPrefix: str, comp: Component, devicedID: str, entitiyID: str, device_class: DeviceClass) -> Topics:

    if comp == Component.SENSOR and isinstance(device_class, BinarySensorDeviceClasses):
        print("getTopics: BinarySensorDeviceClasses angegeben, Component ist aber Sensor, Sensor wird zu BinarySensor abgeändert.")
        comp = Component.BINARY_SENROR

    if discoveryPrefix is not None:
        mainPath = "{0}/{1}/{2}/{3}/".format(discoveryPrefix, str(comp.value), devicedID, entitiyID.replace(" ", "_"))
    else:
        mainPath = "{0}/{1}/{2}/".format(devicedID, comp.value, entitiyID)
    t = Topics(comp, device_class, discoveryPrefix is not None)
    t.state = mainPath + "state"
    t.command = mainPath + "set"
    t.config = mainPath + "config" if discoveryPrefix is not None else None
    t.ava_topic = mainPath + "online"
    return t
