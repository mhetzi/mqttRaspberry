import math
from os import stat
from typing import Union
import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
from Tools.Autodiscovery import SensorDeviceClasses
import logging
import json
from  Tools.PluginManager import PluginManager
from Tools.Devices.Filters import BaseFilter, DontSend, SilentDontSend
import json
import weakref

from Tools.Config import DictBrowser

from time import sleep

class Sensor:
    _mainState = None
    _is_offline = True
    _has_offline = False
    _ignored_counter = -1

    def __init__(self, log:logging.Logger, pman: PluginManager, name: str, sensor_type: SensorDeviceClasses, measurement_unit: str='', ava_topic=None, ownOfflineTopic=False, value_template=None, json_attributes=False, device=None, unique_id=None, icon=None, nodeID=None):
        self._log = log.getChild("Sensor")
        self._log.setLevel(logging.NOTSET)
        self._log.debug("Sensor Object für {} mit custom uid {} erstellt.".format(name, unique_id))
        self._pm = weakref.ref(pman)
        self._name = name
        self._ava_topic = ava_topic
        self._vt = value_template
        self._jsattrib = json_attributes
        self._dev = device
        self._unique_id = unique_id
        self._icon = icon
        self._meassunit = measurement_unit
        self.nodeID = nodeID
        self._topics = pman.config.get_autodiscovery_topic(
            autodisc.Component.SENSOR,
            name,
            sensor_type,
            ownOfflineTopic=ownOfflineTopic,
            node_id=nodeID
        )
        self._playload = None
        self._filters = []
        if ownOfflineTopic or ava_topic is not None:
            self._has_offline = True
    
    def __call__(self, state=None, force_send=False, keypath=None) -> mclient.MQTTMessageInfo:
        return self.state(state=state, force_send=force_send, keypath=keypath)

    def register(self):
        pm = self._pm()
        if pm is None:
            self._log.error("PluginManager is gone!")
            return
        if pm._client is None:
            self._log.error("Tried to register() while MQTT is disconnected!")
            return
        # Setze Discovery Configuration
        self._log.debug("Publish configuration")
        plugin_name = self._log.parent.name
        import re
        safename = re.sub('[\W_]+', '', self._name) 
        uid = "switch.MqttScripts{}.switch.{}.{}".format(pm._client_name, plugin_name, safename) if self._unique_id is None else self._unique_id
        zeroc = self._topics.get_config_payload(
            name=self._name,
            ava_topic=None,
            value_template=self._vt,
            measurement_unit=self._meassunit,
            json_attributes=self._jsattrib,
            device=self._dev,
            unique_id=uid,
            icon=self._icon
        )
        pm._client.publish(self._topics.config, zeroc, retain=True)
        self._log.debug("Publish configuration: {}".format(zeroc))
        pm._client.subscribe(self._topics.command)
        if self._has_offline:
            pm.addOfflineHandler(self.offline)
        self.reset()

    def reset(self):
        self._playload = None
        for filter in self._filters:
            ms = filter.nullOldValues()

    def addFilter(self, filter: BaseFilter):
        self._filters.append(filter)

    def _callFilters(self, ms):
        for filter in self._filters:
            ms = filter.filter(ms)
        if math.isnan(ms):
            raise SilentDontSend
        return ms
        
    def state(self, state=None, force_send=False, keypath=None) -> Union[mclient.MQTTMessageInfo, None]:
        if keypath is not None:
            browse = DictBrowser(state)
            try:
                new_state = browse[keypath]
                self._log.debug(f"Filtering extracted state {new_state}")
                new_state = self._callFilters(new_state)
                browse[keypath] = new_state 
            except SilentDontSend:
                return None
            except DontSend:
                self._log.exception("Filtering failed!")
                return None
        if isinstance(state, dict):
            state = json.dumps(state)
        else:
            try:
                state = self._callFilters(state)
            except SilentDontSend:
                return None
            except DontSend:
                self._log.exception("Filtering failed!")
                return None
        if state is None:
            self._log.warning("state is none")
            return None
        payload = state.encode('utf-8') if self._jsattrib else str(state)
        if self._playload == payload and not force_send:
            self._log.debug("new payload == old payload ignoring...")
            self._ignored_counter = (self._ignored_counter + 1) if self._ignored_counter > -1 else self._ignored_counter
            if self._ignored_counter < 20:
                return None
            self._ignored_counter = 0
        self._playload = payload
        if self._is_offline:
            self._log.debug("Was offline, become online")
            self.online()
            sleep(1)
        self._log.debug(f"Sending on {self._topics.state} payload {payload}")

        pm = self._pm()
        if pm is None:
            self._log.error("PluginManager is gone!")
            return
        if pm._client is None:
            self._log.error("Tried to register() while MQTT is disconnected!")
            return
        
        try:
            return pm._client.publish(self._topics.state, payload=payload)
        except:
            self._log.exception(f"Konnte {payload = } nicht versenden!")

    def resend(self):
        pm = self._pm()
        if pm is None:
            self._log.error("PluginManager is gone!")
            return
        if pm._client is None:
            self._log.error("Tried to register() while MQTT is disconnected!")
            return
        return pm._client.publish(self._topics.state, payload=self._playload)
    
    def offline(self):
        self._is_offline = True

        pm = self._pm()
        if pm is None:
            self._log.error("PluginManager is gone!")
            return
        if pm._client is None:
            self._log.error("Tried to register() while MQTT is disconnected!")
            return
        
        try:
            if self._topics.ava_topic is not None:
                return pm._client.publish(self._topics.ava_topic, payload="offline", retain=True)
        except Exception as e:
            self._log.exception("Markieren des Sensors als offline fehlgeschlagen!")
        return None
    def online(self):
        pm = self._pm()
        if pm is None:
            self._log.error("PluginManager is gone!")
            return
        if pm._client is None:
            self._log.error("Tried to register() while MQTT is disconnected!")
            return
        
        self._is_offline = False
        try:
            if self._topics.ava_topic is not None:
                return pm._client.publish(self._topics.ava_topic, payload="online", retain=True)
        except Exception as e:
            self._log.exception("Markieren des Sensors als online fehlgeschlagen!")
        return None
        