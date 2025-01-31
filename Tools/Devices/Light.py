import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import logging
import json
from  Tools.PluginManager import PluginManager
from Tools.ResettableTimer import ResettableTimer
import enum

class Light:
    _schema = {}
    _state = {}

    def __init__(self, logger:logging.Logger, pman: PluginManager, callback, name: str, ava_topic=None, device=None, unique_id=None, icon=None):
        if not callable(callback):
            raise AttributeError("callback not callable")
        self._log = logger.getChild("Switch")
        self._log.debug("Switch Object für {} mit custom uid {} erstellt.".format(name, unique_id))
        self._pm = pman
        self._callback = callback
        self._name = name
        self._ava_topic = ava_topic
        self._dev = device
        self._unique_id = unique_id
        self._icon = icon
        self._topics = pman.config.get_autodiscovery_topic(
            autodisc.Component.LIGHT,
            name,
            autodisc.DeviceClass()
            )
        self._sendDelay = ResettableTimer(0.25, lambda n: self._pushState(), userval=None, autorun=False)
    
    def enableMireds(self, min, max):
        self._schema["color_temp"] = True
        self._schema["min_mireds"] = min
        self._schema["max_mireds"] = max
        return self

    def enableRgb(self):
        self._schema["rgb"] = True
        return self

    def enableEffects(self, effectList: list):
        self._schema["effect"] = True
        self._schema["effect_list"] = effectList
        return self

    def enablebrightness(self, scale=100):
        self._schema["brightness"] = True
        self._schema["brightness_scale"] = scale
        return self
    
    def enableHs(self):
        self._schema["hs"] = True
        return self

    def enableXy(self):
        self._schema["xy"] = True
        return self

    def enableWhiteValue(self):
        self._schema["white_value"] = True
        return self

    def register(self):
        # Setze Discovery Configuration
        self._log.debug("Publish configuration")
        plugin_name = self._log.parent.name
        import re
        safename = re.sub('[\W_]+', '', self._name) 
        uid = "switch.MqttScripts{}.light.{}.{}".format(self._pm._client_name, plugin_name, safename) if self._unique_id is None else self._unique_id
        
        schema = self._schema.copy()
        schema["schema"] = "json"
        payload = self._topics.get_config_payload(
            self._name, "", ava_topic=None, value_template=None, json_attributes=False, device=self._dev,
            unique_id=uid, icon=self._icon, append_data=schema
        )

        lights_list: list = self._pm.discovery_topics.get("Tools/Devices/Light", [])
        if self._topics.config not in lights_list:
            lights_list.append(self._topics.config)

        self._pm._client.publish(self._topics.config, payload=payload, retain=True)
        self._pm._client.subscribe(self._topics.command)
        self._pm._client.message_callback_add(self._topics.command, lambda client,userdata,message: self._callback(message=message, state_requested=False))

        #Frage Callback nach aktuellen status
        self._callback(state_requested=True, message=None)
    
    def _pushState(self):
        self._pm._client.publish( self._topics.state, payload=json.dumps(self._state) )

    def pushState(self, delayed=None):
        self._sendDelay.reset()

    def brightness(self, on_scale):
        if on_scale > self._schema["brightness_scale"]:
            on_scale = self._schema["brightness_scale"]
        self._state["brightness"] = on_scale
        self.pushState()
    
    def color_temp(self, mired):
        self._state["color_temp"] = mired
        self.pushState()
    
    def rgb(self, r: int, g: int, b: int):
        self._state["color"] = {
            "r": r,
            "g": g,
            "b": b
        }
        self.pushState()
    
    def xy(self, x:int, y:int):
        self._state["color"] = {
            "y": y,
            "x": x,
        }
        self.pushState()
    
    def hs(self, h:int, s:int):
        self._state["color"] = {
            "h": h,
            "s": s,
        }
        self.pushState()

    def effect(self, effect:str):
        self._state["effect"] = effect
        self.pushState()
    
    def onOff(self, on:bool):
        self._state["state"] = "ON" if on else "OFF"
        self.pushState()
    
    def white_value(self, wv):
        self._state["white_value"] = wv