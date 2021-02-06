import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
from Tools.Autodiscovery import SensorDeviceClasses
import logging
import json
from  Tools.PluginManager import PluginManager
import enum
from Tools.Devices.Filters import BaseFilter
import json

class Sensor:
    _mainState = None

    def __init__(self, logger:logging.Logger, pman: PluginManager, name: str, sensor_type: SensorDeviceClasses, measurement_unit: str='', ava_topic=None, value_template=None, json_attributes=False, device=None, unique_id=None, icon=None):
        self._log = logger.getChild("Sensor")
        self._log.debug("Sensor Object für {} mit custom uid {} erstellt.".format(name, unique_id))
        self._pm = pman
        self._name = name
        self._ava_topic = ava_topic
        self._vt = value_template
        self._jsattrib = json_attributes
        self._dev = device
        self._unique_id = unique_id
        self._icon = icon
        self._meassunit = measurement_unit
        self._topics = pman.config.get_autodiscovery_topic(
            autodisc.Component.SENSOR,
            name,
            sensor_type
            )
        self._playload = None
        self._filters = []
    
    def __call__(self, state=None, force_send=False, mainState=None) -> mclient.MQTTMessageInfo:
        return self.state(state=state, force_send=force_send, mainState=mainState)

    def register(self):
        # Setze Discovery Configuration
        self._log.debug("Publish configuration")
        plugin_name = self._log.parent.name
        import re
        safename = re.sub('[\W_]+', '', self._name) 
        uid = "switch.MqttScripts{}.switch.{}.{}".format(self._pm._client_name, plugin_name, safename) if self._unique_id is None else self._unique_id
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
        self._pm._client.publish(self._topics.config, zeroc, retain=True)
        self._log.debug("Publish configuration: {}".format(zeroc))
        self._pm._client.subscribe(self._topics.command)
        self.reset()

    def reset(self):
        self._playload = None

    def addFilter(self, filter: BaseFilter):
        self._filters.append(filter)

    def _compareMainState(self, ms):
        for filter in self._filters:
            ms = filter.filter(ms)
        
    def state(self, state=None, force_send=False, mainState=None) -> mclient.MQTTMessageInfo:
        if mainState is not None:
            mainState = self._compareMainState(mainState)
            if self._mainState == mainState:
                self._mainState = mainState
                return None
        if isinstance(state, dict):
            state = json.dumps(state)
        elif mainState is None:
            mainState = self._compareMainState(state)
            if self._mainState == mainState:
                self._mainState = mainState
                return None
        payload = state.encode('utf-8') if self._jsattrib else state
        if self._playload == payload and not force_send:
            return None
        self._playload = payload
        return self._pm._client.publish(self._topics.state, payload=payload)
