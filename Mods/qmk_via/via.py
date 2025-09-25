import dataclasses
from enum import Enum
from typing import NewType
import io
import json
import ctypes
from ctypes import ArgumentError
import logging

from Tools.Misc import getDictWithContaining
from Mods.qmk_via import CONSTANTS

import hid
 
class QMK_FIELD_ENUM(Enum):
    id_qmk_rgb_matrix_brightness = 1
    id_qmk_rgb_matrix_effect = 2
    id_qmk_rgb_matrix_effect_speed = 3
    id_qmk_rgb_matrix_color = 4

Via_Command_t   = NewType("Via_Command_t", int)
Via_Channels_t  = NewType("Via_Channels_t", int)
Via_Attribute_t = NewType("Via_Attribute_t", int)

@dataclasses.dataclass(slots=True, frozen=True, unsafe_hash=True)
class DeviceConfigEntry:
    friendly_name: str
    vid: int
    pid: int
    ext_via_json: str | None
    embedded_via_json: dict | None

    def get_device_path(self, log:logging.Logger=None) -> str | None:
        for d in hid.enumerate():
            if d.get("vendor_id", 0) == self.vid and d.get("product_id", 0) == self.pid:
                     if log is not None:
                         log.debug(f"Found device for {self.friendly_name}: {d}")
                     if d.get('interface_number', 0) == 1:
                        if log is not None:
                            log.debug(f"Using interface 1 for {self.friendly_name}")
                        return d.get("path", None)
        return None

@dataclasses.dataclass(slots=True, frozen=True)
class KeyboardParsedJson:
    Brightness: tuple[int, int, Via_Attribute_t]
    Effects: tuple[dict[str, int], Via_Attribute_t]
    EffectSpeed: tuple[int, int, Via_Attribute_t]
    # Rows, Cols
    Matrix: tuple[int, int, Via_Attribute_t]
    Color: Via_Attribute_t

def _GetKeyboardDefinitionFromDict(d: dict) -> KeyboardParsedJson:
    bright_data = getDictWithContaining(d, value="id_qmk_rgb_matrix_brightness", value_search_list=True)
    eff_data    = getDictWithContaining(d, value="id_qmk_rgb_matrix_effect", value_search_list=True)
    efs_data    = getDictWithContaining(d, value="id_qmk_rgb_matrix_effect_speed", value_search_list=True)
    matrix      = getDictWithContaining(d, key="matrix")
    color_data  = getDictWithContaining(d, value="id_qmk_rgb_matrix_color", value_search_list=True)

    Brightness: tuple[int, int, Via_Attribute_t] = (0, 255, Via_Attribute_t(CONSTANTS.RGB_MATRIX_VALUE_BRIGHTNESS))
    Effects: tuple[dict[str, int], Via_Attribute_t] = ({}, Via_Attribute_t(CONSTANTS.RGB_MATRIX_VALUE_EFFECT))
    EffectSpeed: tuple[int, int, Via_Attribute_t] = (0, 255, Via_Attribute_t(CONSTANTS.RGB_MATRIX_VALUE_EFFECT_SPEED))
    Matrix: tuple[int, int, Via_Attribute_t] = (1, 1, Via_Attribute_t(CONSTANTS.CHANNEL_RGB_MATRIX))
    Color: Via_Attribute_t = Via_Attribute_t(0)

    if bright_data is not None:
        tup = bright_data.get("options", [0, 255])
        Brightness = (tup[0], tup[1], Via_Attribute_t(CONSTANTS.RGB_MATRIX_VALUE_BRIGHTNESS))
    
    if eff_data is not None:
        tup = eff_data.get("options", [])
        data: dict[str, int] = {}
        for t in tup:
            data[t[0]] = t[1]
        Effects = (data, Via_Attribute_t(CONSTANTS.RGB_MATRIX_VALUE_EFFECT))
    
    if efs_data is not None:
        opt = efs_data.get("options", [])
        EffectSpeed = (opt[0], opt[1], Via_Attribute_t(CONSTANTS.RGB_MATRIX_VALUE_EFFECT_SPEED))
    
    if matrix is not None:
        m: dict = matrix.get("matrix", {})
        Matrix = (m.get("rows", 1), m.get("cols", 1), Via_Attribute_t(CONSTANTS.CHANNEL_RGB_MATRIX))
    if color_data is not None:
        Color = Via_Attribute_t(CONSTANTS.RGB_MATRIX_VALUE_COLOR)

    return KeyboardParsedJson(
        Brightness=Brightness,
        Effects=Effects,
        EffectSpeed=EffectSpeed,
        Matrix=Matrix,
        Color=Color
    )


def GetKeyboardDefinition(keyboard: DeviceConfigEntry) -> KeyboardParsedJson | None:
    if keyboard.embedded_via_json is not None:
        return _GetKeyboardDefinitionFromDict(keyboard.embedded_via_json)
    if keyboard.ext_via_json is not None:
        with io.open(keyboard.ext_via_json, mode="rt", closefd=True) as f:
            data = json.load(fp=f)
            return _GetKeyboardDefinitionFromDict(data)
    return None

class ViaHid:
    def __init__(self, device: DeviceConfigEntry, definition: KeyboardParsedJson, logger: logging.Logger) -> None:
        self._device = device
        self._definition = definition
        self._logger = logger.getChild(f"ViaHid:{device.friendly_name}")
    
    def send(self, command: Via_Command_t, channel: Via_Channels_t|Via_Attribute_t, attribute: Via_Attribute_t, value: int, value2:int=0) -> ctypes.Array[ctypes.c_char] | None:
        p = self._device.get_device_path(self._logger)
        dev = hid.device()
        if dev is None:
            return None
        try:
            dev.open_path(p)
            self._logger.debug(f"Opened device {self._device.friendly_name} at {p}")
            if dev is not None:
                buf = bytearray(32)
                buf[0] = command
                buf[1] = channel
                buf[2] = attribute
                buf[3] = value & 0xFF
                buf[4] = value2 & 0xFF
                dev.write(buf)
                try:
                    return dev.read(32, 500)
                except TypeError:
                    self._logger.warning("Read not supported on this platform/version of hidapi")
                    return dev.read(32)
        except Exception as e:
            self._logger.exception(f"Error sending HID report: {e}")
        finally:
            dev.close()
        return None
    
    def get(self, command: Via_Command_t, attribute: Via_Attribute_t) -> ctypes.Array[ctypes.c_char] | None:
        return self.send(
            command=command,
            channel=attribute,
            attribute=Via_Attribute_t(0),
            value=0
        )

    def get_brightness(self) -> int | None:
        if self._definition.Brightness is None or self._definition.Brightness[1] <= 1:
            return None
        res = self.send(
            command=Via_Command_t(CONSTANTS.CUSTOM_GET_VALUE),
            channel=Via_Channels_t(CONSTANTS.CHANNEL_RGB_MATRIX),
            attribute=self._definition.Brightness[2],
            value=0
        )
        if res is not None and len(res) >= 5:
            self._logger.debug(f"Got brightness response: {res}")
            return res[3]+1
        return None

    def set_brightness(self, brightness: int|None) -> bool:
        if brightness is None:
            return False
        if not (self._definition.Brightness[0] <= brightness <= self._definition.Brightness[1]):
            return False
        res = self.send(
            command=Via_Command_t(CONSTANTS.CUSTOM_SET_VALUE),
            channel=Via_Channels_t(CONSTANTS.CHANNEL_RGB_MATRIX),
            attribute=self._definition.Brightness[2],
            value=brightness
        )
        self._logger.debug(f"Set brightness to {brightness}, response: {res}")
        return res is not None
    
    def get_effect(self) -> str | None:
        effects_dict = self._definition.Effects[0]
        if len(effects_dict) == 0:
            return None
        res = self.send(
            command=Via_Command_t(CONSTANTS.CUSTOM_GET_VALUE),
            channel=Via_Channels_t(CONSTANTS.CHANNEL_RGB_MATRIX),
            attribute=self._definition.Effects[1],
            value=0
        )
        if res is not None and len(res) >= 5:
            effect_value = res[3]
            for k, v in effects_dict.items():
                if v == effect_value:
                    self._logger.debug(f"Got effect response: {res}, effect: {k} ({v})")
                    return k
        return None

    def set_effect(self, effect_name: str) -> bool:
        effects_dict = self._definition.Effects[0]
        if effect_name not in effects_dict:
            self._logger.warning(f"Effect {effect_name} not found in effects list")
            return False
        effect_value = effects_dict[effect_name]
        res = self.send(
            command=Via_Command_t(CONSTANTS.CUSTOM_SET_VALUE),
            channel=Via_Channels_t(CONSTANTS.CHANNEL_RGB_MATRIX),
            attribute=self._definition.Effects[1],
            value=effect_value
        )
        self._logger.debug(f"Set effect to {effect_name} ({effect_value}), response: {res}")
        return res is not None

    def getProtocolVersion(self) -> int | None:
        res = self.send(
            command=Via_Command_t(CONSTANTS.GET_PROTOCOL_VERSION),
            channel=Via_Channels_t(0),
            attribute=Via_Attribute_t(0),
            value=0
        )
        if res is not None and len(res) >= 3:
            version = (res[1] << 8)| res[2]
            self._logger.debug(f"Protocol version: {version}")
            return version
        return None
    
    def setColor(self, hue:int, sat:int):
        if self._definition.Color is None:
            return False
        if not (0 <= hue <= 360) or not (0 <= sat <= 100):
            return False
        res = self.send(
            command=Via_Command_t(CONSTANTS.CUSTOM_SET_VALUE),
            channel=Via_Channels_t(CONSTANTS.CHANNEL_RGB_MATRIX),
            attribute=self._definition.Color,
            value=int(hue/360*255),
            value2=int(sat/100*255)
        )
        self._logger.debug(f"Set color to H:{hue} S:{sat}, response: {res}")
        if res is not None and len(res) >= 4:
            self._logger.debug(f"Response: hue: {int(res[3]/255*360)} sat: {int(res[4]/255*100)}")
        return res is not None
    
    def getColor(self) -> tuple[int, int] | None:
        if self._definition.Color is None:
            return None
        res = self.send(
            command=Via_Command_t(CONSTANTS.CUSTOM_GET_VALUE),
            channel=Via_Channels_t(CONSTANTS.CHANNEL_RGB_MATRIX),
            attribute=self._definition.Color,
            value=0
        )
        if res is not None and len(res) >= 5:
            hue = int(res[3]/255*360)
            sat = int(res[4]/255*100)
            self._logger.debug(f"Got color response: {res}, H:{hue} S:{sat}")
            return (int(hue)+1, int(sat)+1)
        return None
    
@dataclasses.dataclass(slots=True, frozen=True, unsafe_hash=True)
class KeyboardInfo:
    uptime: int # in ms
    layout_options: int
    switch_matrix_state: ctypes.Array[ctypes.c_char] | None
    firmware_version: int
    @staticmethod
    def fromViaHid(via: ViaHid):
        u = via.get(Via_Command_t(CONSTANTS.GET_KEYBOARD_VALUES), Via_Attribute_t(CONSTANTS.id_uptime))
        l = via.get(Via_Command_t(CONSTANTS.GET_KEYBOARD_VALUES), Via_Attribute_t(CONSTANTS.id_layout_options))
        s = via.get(Via_Command_t(CONSTANTS.GET_KEYBOARD_VALUES), Via_Attribute_t(CONSTANTS.id_switch_matrix_state))
        f = via.get(Via_Command_t(CONSTANTS.GET_KEYBOARD_VALUES), Via_Attribute_t(CONSTANTS.id_firmware_version))
        return KeyboardInfo(
            uptime=int.from_bytes(u[2:6], byteorder='big', signed=False) if u is not None and len(u) >= 6 else -1,
            layout_options=int.from_bytes(l[2:6], byteorder='big', signed=False) if l is not None and len(l) >= 6 else -1,
            switch_matrix_state=s,
            firmware_version=int.from_bytes(f[2:6], byteorder='big', signed=False) if f is not None and len(f) >= 6 else -1
        )