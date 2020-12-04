import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import logging
import json
from  Tools.PluginManager import PluginManager
import enum

class BinarySensor:
    def __init__(self, logger:logging.Logger, pman: PluginManager, name: str, binary_sensor_type: autodisc.BinarySensorDeviceClasses, measurement_unit: str='', ava_topic=None, value_template=None, json_attributes=False, device=None, unique_id=None, icon=None):

        self._log = logger.getChild("BinarySensor")
        self._log.debug("BinarySensor Object für {} mit custom uid {} erstellt.".format(name, unique_id))
        self._pm = pman
        self._name = name
        self._ava_topic = ava_topic
        self._vt = value_template
        self._jsattrib = json_attributes
        self._dev = device
        self._unique_id = unique_id
        self._icon = icon
        self._topics = pman.config.get_autodiscovery_topic(
            autodisc.Component.BINARY_SENROR,
            name,
            binary_sensor_type
            )
    
    def register(self):

        # Setze Discovery Configuration
        self._log.debug("Publish configuration")
        plugin_name = self._log.parent.name
        uid = "switch.MqttScripts{}.switch.{}.{}".format(self._pm._client_name, plugin_name, self._name) if self._unique_id is None else self._unique_id
        zeroc = self._topics.get_config_payload(
            name=self._name,
            ava_topic=None,
            value_template=self._vt,
            measurement_unit="",
            json_attributes=self._jsattrib,
            device=self._dev,
            unique_id=uid,
            icon=self._icon
        )
        self._pm._client.publish(self._topics.config, zeroc, retain=True)
        self._pm._client.subscribe(self._topics.command)

    def turn(self, state=None):
        self._pm._client.publish(self._topics.state, payload=state.encode('utf-8'))

    def turnOn(self, json=None):
        if json is not None and self._jsattrib:
            self._log.error("Sending json without declaring json_attributes true. Homeassistant does not like that!")
            raise AttributeError("Sending json without declaring json_attributes true. Homeassistant does not like that!")
        if json is None:
            return self.turn("1")
        self.turn(json)

    def turnOff(self, json=None):
        if json is not None and self._jsattrib:
            self._log.error("Sending json without declaring json_attributes true. Homeassistant does not like that!")
            raise AttributeError("Sending json without declaring json_attributes true. Homeassistant does not like that!")
        if json is None:
            return self.turn("0")
        self.turn(json)