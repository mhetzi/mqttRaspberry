# -*- coding: utf-8 -*-

from os import name
import threading
from Mods.win32submods.pwr.WindowEvents import WindowEventProcessor
from Tools.Autodiscovery import BinarySensorDeviceClasses, SensorDeviceClasses
from time import sleep
from typing import Tuple, Union
from Tools.Config import PluginConfig
from Tools.PluginManager import PluginManager
from Tools.Devices import BinarySensor, Sensor
from Tools.Devices.Filters import DeltaFilter

from logging import Logger
from threading import Thread

import win32con
import win32api
import win32gui
import win32gui_struct
struct = win32gui_struct.struct
pywintypes = win32gui_struct.pywintypes
import time
import ctypes
from ctypes import POINTER, windll, Structure, cast, CFUNCTYPE, c_int, c_uint, c_void_p, c_bool, wintypes
from comtypes import GUID
from ctypes.wintypes import HANDLE, DWORD, BOOL

import Mods.win32submods.pwr.powerevents as pwr

class DeviceManagementMessagesProcessor(pwr.WindowEventReciever):
    
    def __init__(self, window_event_processor: WindowEventProcessor) -> None:
        super().__init__(window_event_processor)
        self._log = window_event_processor._log.getChild("Device")
        
    def on_window_event(self, hwnd, msg, wparam, lparam) -> Union[None, bool]:
            if msg == win32con.WM_DEVICECHANGE:
                self._log.debug(f"wparam: {wparam}, lparam: {lparam}")
                return True
            return None

    def register(self, wasConnected):
        pass

    def sendUpdate(self, force=True):
        pass

    def shutdown(self):
        pass