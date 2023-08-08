import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import logging
import json
from  Tools.PluginManager import PluginManager
import enum

class Button:
    _pm: PluginManager

    def __init__(self, logger:logging.Logger, pman: PluginManager, callback, name: str, measurement_unit: str='', ava_topic=None, value_template=None, json_attributes=False, device=None, unique_id=None, icon=None):
        self._log = logger.getChild("Button")
        self._log.debug("Button Object für {} mit custom uid {} erstellt.".format(name, unique_id))
        self._pm = pman
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
            autodisc.Component.BUTTON,
            name,
            autodisc.DeviceClass()
            )
        if ava_topic is not None:
            self._topics.ava_topic = ava_topic
        self.is_online = ava_topic is None
    
    def __del__(self):
        if self._pm is not None and self._pm._client is not None:
            self._pm._client.message_callback_remove(self._topics.command)

    def _callback(self, message):
        raise NotImplementedError

    def register(self):
        # Setze Discovery Configuration
        self._log.debug("Publish configuration")
        plugin_name = self._log.parent.name if self._log.parent is not None else self._log.name
        import re
        safename = re.sub('[\W_]+', '', self._name) 
        uid = "Button.MqttScripts{}.Button.{}.{}".format(self._pm._client_name, plugin_name, safename) if self._unique_id is None else self._unique_id
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
        self._pm._client.publish(self._topics.config, zeroc, retain=True)
        self._pm._client.subscribe(self._topics.command)
        self._pm._client.message_callback_add(self._topics.command, lambda client,userdata,message: self._callback(message=message))


    def offline(self):
        self.is_online = False
        try:
            return self._pm._client.publish(self._topics.ava_topic, payload="offline", retain=True)
        except:
            self._log.exception("offline(): ")
            return None
    def online(self):
        self.is_online = True
        try:
            return self._pm._client.publish(self._topics.ava_topic, payload="online", retain=True)
        except:
            self._log.exception("online(): ")
            return None