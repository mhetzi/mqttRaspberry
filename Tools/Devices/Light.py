import paho.mqtt.client as mclient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import logging
import json
from  Tools.PluginManager import PluginManager
from Tools.ResettableTimer import ResettableTimer
import enum
from typing import Any
from collections.abc import Callable

class Light:

    callback_type = Callable[[bool, mclient.MQTTMessage | None], None]

    __slot__ = (
        "_log", "_pm", "_callback", "_name", "_ava_topic", "_dev", "_unique_id", "_icon", "_topics", "_sendDelay",
        "_schema", "_state", "is_online", "_last_state"
    )
    _schema = {}
    _state = {}
    is_online = True
    _callback: callback_type | None = None
    _last_state = None

    def __init__(self, logger:logging.Logger, pman: PluginManager, callback: callback_type, name: str, ava_topic=None, device=None, unique_id=None, icon=None):
        if not callable(callback):
            raise AttributeError("callback not callable")
        self._log = logger.getChild("Light")
        self._log.debug("Light Object für {} mit custom uid {} erstellt.".format(name, unique_id))
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
        if ava_topic is not None:
            self._topics.ava_topic = ava_topic
            self._pm.addOfflineHandler(self.offline)
        self._sendDelay = ResettableTimer(1, self._pushState, userval=None, autorun=False)
    
    def enableMireds(self, min, max):
        self._schema["color_temp"] = True
        self._schema["min_mireds"] = min
        self._schema["max_mireds"] = max
        return self

    def enableRgb(self):
        colorMode: list[str] | None = self._schema.get("supported_color_modes", None)
        if colorMode is None:
            colorMode = []
        colorMode += ["rgb"]
        self._schema["supported_color_modes"] = colorMode
        return self

    def enableEffects(self, effectList: list[str]):
        self._schema["effect"] = True
        self._schema["effect_list"] = effectList
        return self

    def enablebrightness(self, scale=100):
        self._schema["brightness"] = True
        self._schema["brightness_scale"] = scale
        return self
    
    def enableHs(self):
        colorMode: list[str] | None = self._schema.get("supported_color_modes", None)
        if colorMode is None:
            colorMode = []
        colorMode += ["hs"]
        self._schema["supported_color_modes"] = colorMode
        return self

    def enableXy(self):
        colorMode: list[str] | None = self._schema.get("supported_color_modes", None)
        if colorMode is None:
            colorMode = []
        colorMode += ["xy"]
        self._schema["supported_color_modes"] = colorMode
        return self

    def enableWhiteValue(self):
        self._schema["white_value"] = True
        return self

    def register(self):
        if self._pm is None or self._pm._client is None:
            raise RuntimeError("PluginManager or MQTT Client is None")
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

        lights_list: list[str] = self._pm.discovery_topics.get("Tools/Devices/Light", [])
        if self._topics.config not in lights_list:
            lights_list.append(self._topics.config)

        self._pm._client.publish(self._topics.config, payload=payload, retain=True)
        self._pm._client.subscribe(self._topics.command)
        self._pm._client.message_callback_add(self._topics.command, self.__call_bootstrap__)

        #Frage Callback nach aktuellen status
        if self._callback is not None:
            self._callback(True, None)
        self.online()
    
    def __call_bootstrap__(self, client: mclient.Client, userdata:Any, message: mclient.MQTTMessage):
        if callable(self._callback):
            self._callback(False, message)

    def _pushState(self):
        if self._pm._client is None:
            self._log.warning("MQTT Client ist None, kann Status nicht senden")
            return
        was_online = self.is_online
        if not was_online:
            self.online()
        if self._state != self._last_state and self.is_online:
            self._pm._client.publish( self._topics.state, payload=json.dumps(self._state) )
            self._last_state = self._state.copy()
            self._sendDelay.cancel()
        if not self.is_online:
            self.pushState(5)

    def pushState(self, delayed: int | None=None):
        self._sendDelay.reset(delayed)

    def brightness(self, on_scale):
        if on_scale > self._schema["brightness_scale"]:
            on_scale = self._schema["brightness_scale"]
        self._state["brightness"] = on_scale
        self.pushState()
    
    def color_temp(self, mired):
        self._state["color_temp"] = mired
        self.pushState()
    
    def rgb(self, r: int, g: int, b: int):
        self._state["color_mode"] = "rgb"
        self._state["color"] = {
            "r": r,
            "g": g,
            "b": b
        }
        self.pushState()
    
    def xy(self, x:int, y:int):
        self._state["color_mode"] = "xy"
        self._state["color"] = {
            "y": y,
            "x": x,
        }
        self.pushState()
    
    def hs(self, h:int, s:int):
        self._state["color_mode"] = "hs"
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

    def offline(self):
        self.is_online = False
        try:
            if self._pm._client is not None and self._topics.ava_topic is not None:
                return self._pm._client.publish(self._topics.ava_topic, payload="offline", retain=True)
        except:
            self._log.exception("offline(): ")
            return None
    def online(self):
        try:
            if self._pm._client is not None and self._topics.ava_topic is not None:
                self.is_online = True
                return self._pm._client.publish(self._topics.ava_topic, payload="online", retain=True)
        except:
            self._log.exception("online(): ")
            return None
    
    def resend(self):
        self.pushState(2)