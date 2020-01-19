import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import logging
import json
from  Tools.PluginManager import PluginManager
import enum

class Switch:
    def __init__(self, logger:logging.Logger, pman: PluginManager, callback, name: str, measurement_unit: str='', ava_topic=None, value_template=None, json_attributes=False, device=None, unique_id=None, icon=None):
        if not callable(callback):
            raise AttributeError("callback not callable")
        self._log = logger.getChild("Switch")
        self._log.debug("Switch Object für {} mit custom uid {} erstellt.".format(name, unique_id))
        self._pm = pman
        self._callback = callback
        self._name = name
        self._munit = measurement_unit
        self._ava_topic = ava_topic
        self._vt = value_template
        self._jsattrib = json_attributes
        self._dev = device
        self._unique_id = unique_id
        self._icon = icon
        self._topics = pman.config.get_autodiscovery_topic(
            autodisc.Component.SWITCH,
            name,
            autodisc.DeviceClass()
            )
    
    def register(self):
        # Setze verfügbarkeit
        ava_topic = self._ava_topic if self._ava_topic is not None else self._topics.ava_topic
        self._log.debug("Publish availibility")
        self._pm._client.will_set(ava_topic, "offline", retain=True)
        self._pm._client.publish(ava_topic, "online", retain=True)

        # Setze Discovery Configuration
        self._log.debug("Publish configuration")
        plugin_name = self._log.parent.name
        uid = "switch.MqttScripts{}.switch.{}.{}".format(self._pm._client_name, plugin_name, self._name) if self._unique_id is None else self._unique_id
        zeroc = self._topics.get_config_payload(
            name=self._name,
            measurement_unit=self._munit,
            ava_topic=self._ava_topic,
            value_template=self._vt,
            json_attributes=self._jsattrib,
            device=self._dev,
            unique_id=uid,
            icon=self._icon
        )
        self._pm._client.publish(self._topics.config, zeroc, retain=True)
        self._pm._client.subscribe(self._topics.command)
        self._pm._client.message_callback_add(self._topics.command, lambda client,userdata,message: self._callback(message=message, state_requested=False))

        #Frage Callback nach aktuellen status
        self._callback(state_requested=True, message=None)

    def turn(self, state=None):
        self._pm._client.publish(self._topics.state, payload=state)

    def turnOn(self, json=None):
        if json is not None and self._jsattrib:
            self._log.error("Sending json without declaring json_attributes true. Homeassistant does not like that!")
            raise AttributeError("Sending json without declaring json_attributes true. Homeassistant does not like that!")
        if json is None:
            self.turn("ON")
        self.turn(json)

    def turnOff(self, json=None):
        if json is not None and self._jsattrib:
            self._log.error("Sending json without declaring json_attributes true. Homeassistant does not like that!")
            raise AttributeError("Sending json without declaring json_attributes true. Homeassistant does not like that!")
        if json is None:
            self.turn("OFF")
        self.turn(json)

class LockState(enum.IntEnum):
    UNLOCK = 0,
    LOCK   = 1

class Lock(Switch):
    def __init__(self, logger:logging.Logger, pman: PluginManager, callback, name: str, measurement_unit: str='', ava_topic=None, value_template=None, json_attributes=False, device=None, unique_id=None, icon=None):
        super().__init__(logger=logger,pman=pman,callable=self.callback_translate,name=name,measurement_unit=measurement_unit, ava_topic=ava_topic,value_template=value_template, json_attributes=json_attributes, device=device, unique_id=unique_id, icon=icon)
        self._topics = pman.config.get_autodiscovery_topic(
            autodisc.Component.LOCK,
            name,
            autodisc.DeviceClass()
        )
        self._cb = callback
        if not callable(callback):
            raise AttributeError("callback not callable")
        
    def lock(self, json=None):
        if json is not None and self._jsattrib:
            self._log.error("Sending json without declaring json_attributes true. Homeassistant does not like that!")
            raise AttributeError("Sending json without declaring json_attributes true. Homeassistant does not like that!")
        if json is None:
            self.turn("locked")
        self.turn(json)

    def unlock(self, json=None):
        if json is not None and self._jsattrib:
            self._log.error("Sending json without declaring json_attributes true. Homeassistant does not like that!")
            raise AttributeError("Sending json without declaring json_attributes true. Homeassistant does not like that!")
        if json is None:
            self.turn("unlocked")
        self.turn(json)
    
    def callback_translate(self, state_requested=False, message=None):
        if state_requested:
            self._cb(state_requested=True, message=None)
        msg = message.payload.decode('utf-8')
        if msg == "LOCK":
            return self._cb(message=LockState.LOCK, state_requested=False)
        self._cb(message=LockState.UNLOCK, state_requested=False)