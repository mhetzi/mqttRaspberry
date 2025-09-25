from Tools import PluginManager
from Tools.Config import BasicConfig, PluginConfig
from Tools.Devices import Light

import logging
import json

from paho.mqtt.client import Client as MqttClient
from paho.mqtt.client import MQTTMessage

from Mods.qmk_via.via import DeviceConfigEntry, KeyboardParsedJson, GetKeyboardDefinition, ViaHid, KeyboardInfo
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
        via = self._vias.get(keyboard, None)
        if via is None:
            self._logger.warning(f"Kann ViaHid für {keyboard.friendly_name} nicht finden!")
            return
        light = self._lights.get(keyboard, None)
        if light is None:
            self._logger.warning(f"Kann Light für {keyboard.friendly_name} nicht finden!")
            return
        
        effect: str | None = js.get("effect", None)
        state: str | None = js.get("state", None)
        bright: int | None = js.get("brightness", None)
        color: dict | None = js.get("color", None)

        if state is not None:
            light.onOff(state == "ON")
            if effect is None and state == "OFF":
                via.set_effect("None")

        if bright is not None:
            via.set_brightness(bright)
            light.brightness(bright)

        if effect is not None:
            light.effect(effect)
            via.set_effect(effect)

        if color is not None:
            if "h" in color and "s" in color:
                h = color.get("h", 0)
                s = color.get("s", 0)
                light.hs(h, s)
                via.setColor(h, s)

        pass

    def register(self, newClient: MqttClient, wasConnected=False):
        if not wasConnected:
            self._lights.clear()
            for keyboard in self._keyboards:
                licht = Light.Light(
                    logger=self._logger,
                    pman=self._pluginManager,
                    callback=lambda state_requested, message: self.light_call(message=message, keyboard=keyboard, state_requested=state_requested),
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

                ki = KeyboardInfo.fromViaHid(self._vias[keyboard])
                self._logger.info(f"Keyboard {keyboard.friendly_name} info: {ki=}")
                
                self._logger.info(f"Keyboard {keyboard.friendly_name} protocol: {proto}")
        
        for licht in self._lights.values():
            licht.register()

    def stop(self):
        pass

    def sendStates(self):
        pass