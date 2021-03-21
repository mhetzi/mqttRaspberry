# -*- coding: utf-8 -*-

import threading
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
import wmi

### CONSTANTS
PBT_POWERSETTINGCHANGE = 0x8013
GUID_CONSOLE_DISPLAY_STATE = '{6FE69556-704A-47A0-8F24-C28D936FDA47}'
GUID_ACDC_POWER_SOURCE = '{5D3E9A59-E9D5-4B00-A6BD-FF34FF516548}'
GUID_BATTERY_PERCENTAGE_REMAINING = '{A7AD8041-B45A-4CAE-87A3-EECBB468A9E1}'
GUID_MONITOR_POWER_ON = '{02731015-4510-4526-99E6-E5A17EBD1AEA}'
GUID_SYSTEM_AWAYMODE = '{98A7F580-01F7-48AA-9C0F-44352C29E5C0}'
GUID_SESSION_USER_PRESENCE = '{3C0F4548-C03F-4C4D-B9F2-237EDE686376}'

class POWERBROADCAST_SETTING(Structure):
    _fields_ = [("PowerSetting", GUID),
                ("DataLength", DWORD),
                ("Data", DWORD)]

class Powerevents:
    _shutdown = False
    _pman: Union[PluginConfig,None] = None
    _handles: dict[str, int] = {}
    # Map from GUID to Sensor
    _sensors: dict[str, BinarySensor.BinarySensor] = {}
    _states: dict[str, Union[bool,int]] = {}
    _guids_info: dict[str, str] = {}
    __hwnd: Union[int,None] = 0

    def __init__(self, config: PluginConfig, log: Logger) -> None:
        self._config = PluginConfig(config, "pwr")
        self._log = log.getChild("PWR")

        def wndproc(hwnd, msg, wparam, lparam):
            try:
                if msg == win32con.WM_POWERBROADCAST:
                    if wparam == win32con.PBT_APMPOWERSTATUSCHANGE:
                        self._log.debug('Power status has changed')
                    if wparam == win32con.PBT_APMRESUMEAUTOMATIC:
                        self._log.debug('System resume')
                    if wparam == win32con.PBT_APMRESUMESUSPEND:
                        self._log.debug('System resume by user input')
                    if wparam == win32con.PBT_APMSUSPEND:
                        self._log.debug('System suspend')
                    if wparam == PBT_POWERSETTINGCHANGE:
                        self._log.debug('Power setting changed...')
                        settings = cast(lparam, POINTER(POWERBROADCAST_SETTING)).contents
                        power_setting = str(settings.PowerSetting)
                        data_length = settings.DataLength
                        data = settings.Data
                        self.powerSettingsChanged(power_setting=power_setting, data=data)
                    return True

                return False
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
            hwnd = None
            try:
                myWindowClass = win32gui.RegisterClass(wndclass)
                hwnd = win32gui.CreateWindowEx(win32con.WS_EX_LEFT,
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

            self.__hwnd = hwnd
            if hwnd is None:
                self._log.error("hwnd is none!")
                return
            else:
                self._log.debug("Windows Handle ({}) erstellt".format(hwnd))

            self._guids_info = self._config.get("enabled_guids", {
                'Monitor' : GUID_MONITOR_POWER_ON,
                'System Away' : GUID_SYSTEM_AWAYMODE,
                'Konsolenfenster Status' : GUID_CONSOLE_DISPLAY_STATE,
                'ACDC Stromversorgung' : GUID_ACDC_POWER_SOURCE,
                'Batterie %' : GUID_BATTERY_PERCENTAGE_REMAINING,
                'Benutzeranwesenheit': GUID_SESSION_USER_PRESENCE
            })
            for name, guid_info in self._guids_info.items():
                result = windll.user32.RegisterPowerSettingNotification(HANDLE(hwnd), GUID(guid_info), DWORD(0))
                self._handles[name] = result
                self._log.info("PowerNotification {} Regestriert: GUID {}, Handle: {}, Fehler: {}".format(name, guid_info, hex(result), win32api.GetLastError()))

            self._log.debug("Begin pumping...")
            try:
                while not self._shutdown:
                    win32gui.PumpWaitingMessages()
                    time.sleep(1)
            except:
                self._log.exception("Pumping of messages failed")

        self._window_pump_thread = threading.Thread(name="window_pump", target=window_pump)
        self._window_pump_thread.start()

    def register(self, wasConnected: bool, pman: PluginManager):
        self._pman = pman

        if not wasConnected:
            for name, guid in self._guids_info.items():
                devc = BinarySensorDeviceClasses.GENERIC_SENSOR
                if guid == GUID_MONITOR_POWER_ON:
                    devc = BinarySensorDeviceClasses.POWER
                elif guid == GUID_ACDC_POWER_SOURCE:
                    devc = BinarySensorDeviceClasses.PLUG
                elif guid == GUID_SESSION_USER_PRESENCE:
                    devc = BinarySensorDeviceClasses.PRESENCE
                
                if guid == GUID_BATTERY_PERCENTAGE_REMAINING:
                    devc = Sensor.SensorDeviceClasses.BATTERY
                    dev = Sensor.Sensor(
                        self._log, self._pman,
                        name, devc, "%"
                    )
                    dev.addFilter( DeltaFilter.DeltaFilter(1, self._log) )
                    dev.register()
                    if guid in self._states.keys():
                        dev.state(self._states[guid])
                else:
                    dev = BinarySensor.BinarySensor(
                        self._log, self._pman,
                        name, devc
                    )
                    dev.register()
                    if guid in self._states.keys():
                        dev.turnOnOff(self._states[guid])
                self._sensors[guid] = dev
        self.sendUpdate(not wasConnected)

    def sendUpdate(self, force=True):
        for uid, data in self._states.items():
            self.powerSettingsChanged(uid, data)
    
    def shutdown(self):
        self._shutdown = True
        self._window_pump_thread.join()
        for hndl in self._handles.values():
            windll.user32.UnregisterPowerSettingNotification(hndl)
        
    def powerSettingsChanged(self, power_setting, data):
        if power_setting == GUID_CONSOLE_DISPLAY_STATE:
            if data == 0: self._log.debug('  Display off')
            elif data == 1: self._log.debug('  Display on')
            elif data == 2: self._log.debug('  Display dimmed')
            self._states[GUID_CONSOLE_DISPLAY_STATE] = data != 0
            if GUID_CONSOLE_DISPLAY_STATE in self._sensors.keys():
                dev = self._sensors[GUID_CONSOLE_DISPLAY_STATE]
                dev.turnOnOff(data != 0)
        elif power_setting == GUID_ACDC_POWER_SOURCE:
            if data == 0: self._log.debug('  AC power')
            elif data == 1: self._log.debug('  Battery power')
            elif data == 2: self._log.debug('  Short term power')
            self._states[GUID_ACDC_POWER_SOURCE] = data != 0
            if GUID_ACDC_POWER_SOURCE in self._sensors.keys():
                dev = self._sensors[GUID_ACDC_POWER_SOURCE]
                dev.turnOnOff(data != 0)
        elif power_setting == GUID_BATTERY_PERCENTAGE_REMAINING:
            self._log.debug('  battery remaining: %s' % data)
            self._states[GUID_BATTERY_PERCENTAGE_REMAINING] = int(data)
            if GUID_BATTERY_PERCENTAGE_REMAINING in self._sensors.keys():
                dev = self._sensors[GUID_BATTERY_PERCENTAGE_REMAINING]
                dev(int(data))
        elif power_setting == GUID_MONITOR_POWER_ON:
            if data == 0: self._log.debug('  Monitor off')
            elif data == 1: self._log.debug('  Monitor on')
            self._states[GUID_MONITOR_POWER_ON] = data != 0
            if GUID_MONITOR_POWER_ON in self._sensors.keys():
                dev = self._sensors[GUID_MONITOR_POWER_ON]
                dev.turnOnOff(data != 0)
                
        elif power_setting == GUID_SYSTEM_AWAYMODE:
            if data == 0: self._log.debug('  Exiting away mode')
            elif data == 1: self._log.debug('  Entering away mode')
            self._states[GUID_SYSTEM_AWAYMODE] = data != 0
            if GUID_SYSTEM_AWAYMODE in self._sensors.keys():
                dev = self._sensors[GUID_SYSTEM_AWAYMODE]
                dev.turnOnOff(data != 0)
        elif power_setting == GUID_SESSION_USER_PRESENCE:
            if data == 0: self._log.debug('  User present')
            elif data == 2: self._log.debug('  User not present')
            self._states[GUID_SESSION_USER_PRESENCE] = data == 0
            if GUID_SESSION_USER_PRESENCE in self._sensors.keys():
                dev = self._sensors[GUID_SESSION_USER_PRESENCE]
                dev.turnOnOff(data == 0)
        else:
            self._log.debug('unknown GUID ({}, {})'.format(power_setting, GUID_SESSION_USER_PRESENCE))