import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import logging
import json
from  Tools.PluginManager import PluginManager
import enum
from Tools.Devices.Switch import Switch

class LockState(enum.IntEnum):
    UNLOCK = 0,
    LOCK   = 1

class Lock(Switch):
    def __init__(self, logger:logging.Logger, pman: PluginManager, callback, name: str, measurement_unit: str='', ava_topic=None, value_template=None, json_attributes=False, device=None, unique_id=None, icon=None):
        super().__init__(logger=logger,pman=pman,callback=self.callback_translate,name=name,measurement_unit=measurement_unit, ava_topic=ava_topic,value_template=value_template, json_attributes=json_attributes, device=device, unique_id=unique_id, icon=icon)
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
            return self.turn("LOCKED")
        self.turn(json)

    def unlock(self, json=None):
        if json is not None and self._jsattrib:
            self._log.error("Sending json without declaring json_attributes true. Homeassistant does not like that!")
            raise AttributeError("Sending json without declaring json_attributes true. Homeassistant does not like that!")
        if json is None:
            return self.turn("UNLOCKED")
        self.turn(json)
    
    def callback_translate(self, state_requested=False, message=None):
        if state_requested:
            return self._cb(state_requested=True, message=None)
        msg = message.payload.decode('utf-8')
        if msg == "LOCK":
            return self._cb(message=LockState.LOCK, state_requested=False)
        self._cb(message=LockState.UNLOCK, state_requested=False)