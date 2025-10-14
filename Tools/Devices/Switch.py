import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import logging
import json
from  Tools.PluginManager import PluginManager
import enum
import weakref

class Switch:
    _pm: weakref.ReferenceType[PluginManager]
    _last_state = None

    def __init__(self, logger:logging.Logger, pman: PluginManager, callback, name: str, measurement_unit: str='', ava_topic=None, value_template=None, json_attributes=False, device=None, unique_id=None, icon=None):
        self._log = logger.getChild("Switch")
        self._log.debug("Switch Object für {} mit custom uid {} erstellt.".format(name, unique_id))
        self._pm = weakref.ref(pman)
        if callable(callback):
            self._callback = callback
        self._name = name
        self._munit = measurement_unit
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
        if ava_topic is not None:
            self._topics.ava_topic = ava_topic
        self.is_online = ava_topic is None
    
    def __del__(self):
        pm = self._pm()
        if pm is not None and pm._client is not None:
            pm._client.message_callback_remove(self._topics.command)

    def _callback(self, message, state_requested=False):
        raise NotImplementedError

    def register(self):
        pm = self._pm()
        if pm is None:
            self._log.error("PluginManager is gone!")
            return
        if pm._client is None:
            self._log.error("Called register() when no MQTT connection is done!")
            return

        # Setze Discovery Configuration
        self._log.debug("Publish configuration")
        plugin_name = self._log.parent.name if self._log.parent is not None else self._log.name
        import re
        safename = re.sub('[\W_]+', '', self._name) 
        uid = "switch.MqttScripts{}.switch.{}.{}".format(pm._client_name, plugin_name, safename) if self._unique_id is None else self._unique_id
        zeroc = self._topics.get_config_payload(
            name=self._name,
            measurement_unit=self._munit,
            ava_topic=None,
            value_template=self._vt,
            json_attributes=self._jsattrib,
            device=self._dev,
            unique_id=uid,
            icon=self._icon
        )
        pm._client.publish(self._topics.config, zeroc, retain=True)
        pm._client.subscribe(self._topics.command)
        pm._client.message_callback_add(self._topics.command, lambda client,userdata,message: self._callback(message=message, state_requested=False))

        #Frage Callback nach aktuellen status
        self._callback(state_requested=True, message=None)
        if self._topics.ava_topic is not None:
            pm.addOfflineHandler(self.offline)

        if self._last_state is not None:
            self.turn()

    def turn(self, state=None, qos=0):
        if state is None and self._last_state is None:
            return
        if state is None:
            state = self._last_state
        if state is None:
            self._log.error("Publish state failed! No state or last_state available!")
            self.offline()
            return
        if not self.is_online:
            self.online()
        if isinstance(state, dict):
            state = json.dumps(state)
        elif isinstance(state, bool):
            state = "ON" if state else "OFF"
        self._last_state = state
        payload = state.encode('utf-8')

        pm = self._pm()
        if pm is None:
            self._log.error("PluginManager is gone!")
            return
        if pm._client is None:
            self._log.error("Called register() when no MQTT connection is done!")
            return
        self._log.debug(f"Switch \n{self._topics.state =} \n{payload =}")
        return pm._client.publish(self._topics.state, payload=payload,qos=qos)

    def turnOn(self, json=None, qos=0):
        if json is not None and not self._jsattrib:
            self._log.error("Sending json without declaring json_attributes true. Homeassistant does not like that!")
            raise AttributeError("Sending json without declaring json_attributes true. Homeassistant does not like that!")
        if json is None:
            return self.turn("ON")
        return self.turn(json, qos=qos)

    def turnOff(self, json=None, qos=0):
        if json is not None and not self._jsattrib:
            self._log.error("Sending json without declaring json_attributes true. Homeassistant does not like that!")
            raise AttributeError("Sending json without declaring json_attributes true. Homeassistant does not like that!")
        if json is None:
            return self.turn("OFF")
        return self.turn(json, qos=qos)
    
    def turnOnOff(self, state:bool, qos=0):
        if state:
            return self.turnOn(qos=qos)
        self.turnOff(qos=qos)

    def offline(self):
        self.is_online = False
        pm = self._pm()
        if pm is None:
            self._log.error("PluginManager is gone!")
            return
        if pm._client is None:
            self._log.error("Called register() when no MQTT connection is done!")
            return
        try:
            if pm._client is not None and self._topics.ava_topic is not None:
                return pm._client.publish(self._topics.ava_topic, payload="offline", retain=True)
        except:
            self._log.exception("offline(): ")
            return None
    def online(self):
        pm = self._pm()
        if pm is None:
            self._log.error("PluginManager is gone!")
            return
        if pm._client is None:
            self._log.error("Called register() when no MQTT connection is done!")
            return
        self.is_online = True
        try:
            if pm._client is not None and self._topics.ava_topic is not None:
                return pm._client.publish(self._topics.ava_topic, payload="online", retain=True)
        except:
            self._log.exception("online(): ")
            return None
    
    def resend(self):
        self.turn(self._last_state)