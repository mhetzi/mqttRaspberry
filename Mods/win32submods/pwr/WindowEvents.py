# -*- coding: utf-8 -*-

from abc import abstractmethod
from os import name
import threading
from Tools.Autodiscovery import BinarySensorDeviceClasses, SensorDeviceClasses
from time import sleep
from typing import Tuple, Union
from Tools.Config import PluginConfig
from Tools.PluginManager import PluginInterface, PluginManager
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

from Mods.win32submods.pwr.WindowEventReceiverInterface import WindowEventReciever

class WindowEventProcessor:
    _shutdown = False
    _pman: Union[PluginManager,None] = None
    _hwnd: Union[int,None] = 0
    _window_message_receivers: list[WindowEventReciever] = []

    def __init__(self, config: PluginConfig, log: Logger) -> None:
        self._config = PluginConfig(config, "pwr")
        self._log = log.getChild("WindowMessages")

        if self._config.get("pwr", True):
            from Mods.win32submods.pwr.powerevents import Powerevents
            pe = Powerevents(self)
            self._window_message_receivers.append(pe)
        if self._config.get("dev", True):
            from Mods.win32submods.pwr.pwr_devices import DeviceManagementMessagesProcessor
            pe = DeviceManagementMessagesProcessor(self)
            self._window_message_receivers.append(pe)

        def wndproc(hwnd, msg, wparam, lparam):
            for rec in self._window_message_receivers:
                try:
                    val = rec.on_window_event(hwnd, msg, wparam, lparam)
                    if val is not None:
                        return val
                except:
                    self._log.exception("wndproc")

        def window_pump():
            self._log.debug("Win32 API Window erstellen...")
            hinst = win32api.GetModuleHandle(None)
            wndclass = win32gui.WNDCLASS()
            wndclass.hInstance = hinst
            wndclass.lpszClassName = "mqttScriptPowereventWindowClass"
            CMPFUNC = CFUNCTYPE(c_bool, c_int, c_uint, c_uint, c_void_p)
            wndproc_pointer = CMPFUNC(wndproc)
            wndclass.lpfnWndProc = {win32con.WM_POWERBROADCAST : wndproc_pointer}
            try:
                myWindowClass = win32gui.RegisterClass(wndclass)
                self._hwnd = win32gui.CreateWindowEx(win32con.WS_EX_LEFT,
                                            myWindowClass, 
                                            "mqttScriptPowereventWindow", 
                                            0, 
                                            0, 
                                            0, 
                                            win32con.CW_USEDEFAULT, 
                                            win32con.CW_USEDEFAULT, 
                                            win32con.HWND_MESSAGE, 
                                            0, 
                                            hinst, 
                                            None)
            except Exception as e:
                self._log.exception("Window konnte nicht erstellt werden!")

            if self._hwnd is None:
                self._log.error("hwnd is none!")
                return
            else:
                self._log.debug("Windows Handle ({}) erstellt".format(self._hwnd))
            self._log.debug("Begin pumping...")
            try:
                while not self._shutdown:
                    win32gui.PumpWaitingMessages()
                    time.sleep(1)
            except:
                self._log.exception("Pumping of messages failed")

        self._window_pump_thread = threading.Thread(name="window_pump", target=window_pump)
        self._window_pump_thread.start()

    def killPluginManager(self):
        if self._pman is None:
            self._log.error("Shutdown on windows shutdown failed!")
            return
        import threading
        t = threading.Thread(target=self._pman.shutdown, name="WindowsAsyncDestroy", daemon=True)
        t.start()
    
    def register(self, wasConnected: bool, pman: PluginManager):
        self._pman = pman
        for rec in self._window_message_receivers:
            rec.register(wasConnected=wasConnected)
    
    def shutdown(self):
        try:
            for rec in self._window_message_receivers:
                rec.shutdown()
        except:
            self._log.exception("Shutdown of WindowEvent extension failed!")
        self._log.debug("WindowEvent wait4shutdown...")
        self._shutdown = True
        self._window_pump_thread.join()
    
    def sendUpdate(self, force=True):
        try:
            for rec in self._window_message_receivers:
                rec.sendUpdate(force=force)
        except:
            self._log.exception("sendUpdate()")