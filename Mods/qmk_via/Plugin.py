from Tools import PluginManager
from Tools.Config import BasicConfig, PluginConfig
from Tools.Devices import Light

import logging
import json

from paho.mqtt.client import Client as MqttClient
from paho.mqtt.client import MQTTMessage

from Mods.qmk_via.via import DeviceConfigEntry, KeyboardParsedJson, GetKeyboardDefinition, ViaHid, Via_Command_t, Via_Channels_t, Via_Attribute_t
from Mods.qmk_via import CONSTANTS

class ViaPlugin(PluginManager.PluginInterface):
    _lights: dict[DeviceConfigEntry, Light.Light] = {}
    _keyboards: list[DeviceConfigEntry] = []
    _keyboard_defs: dict[DeviceConfigEntry, KeyboardParsedJson] = {}
    _vias: dict[DeviceConfigEntry, ViaHid] = {}

    def __init__(self, client: MqttClient, opts: PluginConfig, logger: logging.Logger, device_id: str):
        self._config = opts
        self._client = client
        self._logger = logger
        self._device_id = device_id
        keyboards: list[dict] = self._config.get("keyboards", []) # pyright: ignore[reportAssignmentType]
        for keyboard in keyboards:
            self._logger.debug(f"Loading keyboard config: {keyboard}")
            vid: int = keyboard.get("vid", 0)
            pid: int = keyboard.get("pid", 0)
            js_file: str | None = keyboard.get("jsstr", None)
            js_embedded: dict | None = keyboard.get("embedded", None)
            self._keyboards.append(DeviceConfigEntry(
                friendly_name=keyboard.get("fname", f"QMK_VIA:{vid}_{pid}"),
                vid=vid,
                pid=pid,
                ext_via_json=js_file,
                embedded_via_json=js_embedded
            ))
    
    def set_pluginManager(self, pm: PluginManager.PluginManager):
        self._pluginManager = pm

    def light_call(self, message: MQTTMessage, keyboard: DeviceConfigEntry, state_requested: bool):
        # {"state":"ON","brightness":102}
        if message is None:
            return
        if message.payload is None:
            self._logger.info(f"From {message=} | the attribute {message.payload=}")
            return
        dec_msg = message.payload.decode('utf-8')
        self._logger.debug(f"Decoded message: {dec_msg}")
        js = json.loads(dec_msg)
        if js is None:
            return
        bright = js.get("brightness", None)
        if js.get("state", None) is not None:
            state = js.get("state", "OFF")
            if state == "ON":
                state = 1
                bright = 255 if bright is None else bright
            else:
                state = 0
                bright = 0
        self._logger.debug(f"Set keyboard {keyboard.friendly_name} to state {state} with brightness {bright}")
        via = self._vias.get(keyboard, None)
        if via is None:
            self._logger.warning(f"Kann ViaHid für {keyboard.friendly_name} nicht finden!")
            return
        via.set_brightness(bright)
        light = self._lights.get(keyboard, None)
        effect = js.get("effect", None)
        if effect is not None:
            if light is not None:
                light.effect(effect)
                via.set_effect(effect)
        elif light is not None:
            light.onOff(state==1)
            light.brightness(bright)
        pass

    def register(self, newClient: MqttClient, wasConnected=False):
        if not wasConnected:
            self._lights.clear()
            for keyboard in self._keyboards:
                licht = Light.Light(
                    logger=self._logger,
                    pman=self._pluginManager,
                    callback=lambda message, state_requested: self.light_call(message=message, keyboard=keyboard, state_requested=state_requested),
                    name=keyboard.friendly_name
                )
                d = GetKeyboardDefinition(keyboard)
                if d is None:
                    self._logger.warning(f"Kann Tastaturdefinition für {keyboard.friendly_name} nicht laden!")
                    continue
                self._vias[keyboard] = ViaHid(keyboard, d, self._logger)
                self._keyboard_defs[keyboard] = d
                if d.Brightness[1] > 0:
                    licht.enablebrightness(d.Brightness[1])
                    b = self._vias[keyboard].get_brightness()
                    if b is not None:
                        licht.brightness(b)
                if len(d.Effects[0]) > 0:
                    licht.enableEffects(list(d.Effects[0].keys()))
                    e = self._vias[keyboard].get_effect()
                    if e is not None:
                        licht.effect(e)
                if d.Color > 0:
                    licht.enableHs()
                    hs = self._vias[keyboard].getColor()
                    if hs is not None:
                        licht.hs(hs[0], hs[1])
                self._lights[keyboard] = licht
                proto = self._vias[keyboard].getProtocolVersion()

                
                self._logger.info(f"Keyboard {keyboard.friendly_name} protocol: {proto}")
        
        for licht in self._lights.values():
            licht.register()

    def stop(self):
        pass

    def sendStates(self):
        pass