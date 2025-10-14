from Tools import PluginManager
from Tools.Config import BasicConfig, PluginConfig
from Tools.Devices import Light, Number
from Tools.Autodiscovery import SensorDeviceClasses, DeviceInfo, Topics
from uuid import uuid4

import logging
import json

from paho.mqtt.client import MQTTMessage

from Mods.qmk_via.via import DeviceConfigEntry, KeyboardParsedJson, GetKeyboardDefinition, ViaHid, KeyboardInfo
import schedule

class ViaPlugin(PluginManager.PluginInterface):
    _lights: dict[DeviceConfigEntry, Light.Light] = {}
    _eff_speeds: dict[DeviceConfigEntry, Number.Number] = {}
    _keyboards: list[DeviceConfigEntry] = []
    _keyboard_defs: dict[DeviceConfigEntry, KeyboardParsedJson] = {}
    _vias: dict[DeviceConfigEntry, ViaHid] = {}
    _sched_job: schedule.Job | None = None
    _polling_interval: int = 10

    def __init__(self, opts: PluginConfig, logger: logging.Logger):
        self._config = opts
        self._logger = logger
        keyboards: list[dict] = self._config.get("keyboards", []) # pyright: ignore[reportAssignmentType]
        self._polling_interval = self._config.getExact("polling_every_seconds", self._polling_interval)
        self._keyboards.clear()

        for keyboard in keyboards:
            self._logger.debug(f"Loading keyboard config: {keyboard}")
            vid: int = keyboard.get("vid", 0)
            pid: int = keyboard.get("pid", 0)
            uid: str | None = keyboard.get("uid", None)
            if uid is None or len(uid) == 0:
                uid = str(uuid4())
                keyboard["uid"] = uid
            js_file: str | None = keyboard.get("jsstr", None)
            js_embedded: dict | None = keyboard.get("embedded", None)
            self._keyboards.append(DeviceConfigEntry(
                friendly_name=keyboard.get("fname", f"QMK_VIA:{vid}_{pid}"),
                vid=vid,
                pid=pid,
                ext_via_json=js_file,
                embedded_via_json=js_embedded,
                uid=uid
            ))
    
    def disconnected(self):
        return super().disconnected()

    def set_pluginManager(self, pm: PluginManager.PluginManager):
        self._pluginManager = pm

    def effect_speed_call(self, message: MQTTMessage, keyboard: DeviceConfigEntry, state_requested: bool):
        if message is None:
            return
        if message.payload is None:
            self._logger.info(f"From {message=} | the attribute {message.payload=}")
            return
        dec_msg = message.payload.decode('utf-8')
        self._logger.debug(f"Decoded message: {dec_msg}")
        try:
            val = int(dec_msg)
        except ValueError:
            self._logger.warning(f"Cannot convert {dec_msg} to int")
            return
        via = self._vias.get(keyboard, None)
        if via is None:
            self._logger.warning(f"Kann ViaHid für {keyboard.friendly_name} nicht finden!")
            return
        eff = self._eff_speeds.get(keyboard, None)
        if eff is None:
            self._logger.warning(f"Kann Number für {keyboard.friendly_name} nicht finden!")
            return
        d = self._keyboard_defs.get(keyboard, None)
        if d is None:
            self._logger.warning(f"Kann Tastaturdefinition für {keyboard.friendly_name} nicht finden!")
            return
        if d.EffectSpeed[1] <= 0:
            self._logger.warning(f"Tastaturdefinition für {keyboard.friendly_name} unterstützt keine Effektgeschwindigkeit!")
            return
        if val < 0 or val > d.EffectSpeed[1]:
            self._logger.warning(f"Wert {val} außerhalb des gültigen Bereichs 0..{d.EffectSpeed[1]} für {keyboard.friendly_name}!")
            return
        via.set_effect_speed(int(val))
        eff.state(int(val))
        pass

    def light_call(self, message: MQTTMessage | None, keyboard: DeviceConfigEntry, state_requested: bool):
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

    def register(self, wasConnected=False):
        if self._pluginManager is None:
            self._logger.error(f"{self._pluginManager=} it should not be none")
            return
        if not wasConnected:
            self._lights.clear()
            self._eff_speeds.clear()
            for keyboard in self._keyboards:
                d = GetKeyboardDefinition(keyboard)
                if d is None:
                    self._logger.warning(f"Kann Tastaturdefinition für {keyboard.friendly_name} nicht laden!")
                    continue
                self._vias[keyboard] = ViaHid(keyboard, d, self._logger)
                self._keyboard_defs[keyboard] = d
                
                ki = KeyboardInfo.fromViaHid(self._vias[keyboard])
                hid_data = keyboard.get_hid_info(self._logger)
                hid_data = {} if hid_data is None else hid_data
                kuid = keyboard.uid if keyboard.uid is not None else f"{keyboard.vid:04X}:{keyboard.pid:04X}"

                di = DeviceInfo(
                    IDs = [kuid , f"{keyboard.vid:04X}:{keyboard.pid:04X}" ],
                    pi_serial = None,
                    mfr=hid_data.get("manufacturer_string", "Unknown"),
                    model=hid_data.get("product_string", "Unknown"),
                    sw_version=f"FW: {ki.firmware_version} PROTO: {self._vias[keyboard].getProtocolVersion()}",
                    name=keyboard.friendly_name,
                    via_device=Topics.get_std_devInf().IDs[0] if Topics.get_std_devInf() is not None else None
                )

                licht = Light.Light(
                    logger=self._logger,
                    pman=self._pluginManager,
                    callback=lambda state_requested, message: self.light_call(message=message, keyboard=keyboard, state_requested=state_requested),
                    name=keyboard.friendly_name,
                    device=di,
                    ava_topic=f"qmk_via/{kuid}/available"
                )

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

                if d.EffectSpeed[1] > 0:
                    eff = Number.Number(
                        logger=self._logger,
                        pman=self._pluginManager,
                        callback=lambda state_requested, message: self.effect_speed_call(message=message, keyboard=keyboard, state_requested=state_requested),
                        name=f"{keyboard.friendly_name} Effect Speed",
                        device_class=SensorDeviceClasses.GENERIC_SENSOR,
                        device=di,
                        ava_topic=f"qmk_via/{kuid}/available"
                    )
                    eff.step = 1
                    eff.min = d.EffectSpeed[0]
                    eff.max = d.EffectSpeed[1]
                    self._eff_speeds[keyboard] = eff
                    es = self._vias[keyboard].get_effect_speed()
                    if es is not None:
                        eff.state(es)

                proto = self._vias[keyboard].getProtocolVersion()

                self._logger.info(f"Keyboard {keyboard.friendly_name} info: {ki=}")
                
                self._logger.info(f"Keyboard {keyboard.friendly_name} protocol: {proto}")
        
        for licht in self._lights.values():
            licht.register()
        for eff in self._eff_speeds.values():
            eff.register()
        
        if self._sched_job is None:
            self._sched_job = schedule.every(self._polling_interval).seconds.do(self.sendStates)

    def stop(self):
        pass

    def sendStates(self):
        for keyboard in self._keyboards:
            light = self._lights.get(keyboard, None)
            if light is not None:
                if not self._vias[keyboard].isConnected():
                    light.offline()
                    continue
                
                b = self._vias[keyboard].get_brightness()
                if b is not None:
                    light.brightness(b)
                e = self._vias[keyboard].get_effect()
                if e is not None:
                    light.effect(e)
                if b is not None and (e is None or e == "None"):
                    light.onOff(False)
                else:
                    light.onOff(True)
            eff = self._eff_speeds.get(keyboard, None)
            if eff is not None:
                if not self._vias[keyboard].isConnected():
                    eff.offline()
                    continue
                es = self._vias[keyboard].get_effect_speed()
                if es is not None:
                    eff.state(es)
