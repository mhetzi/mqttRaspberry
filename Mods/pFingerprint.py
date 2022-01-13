# -*- coding: utf-8 -*-
from time import sleep
from typing import Union
from typing_extensions import Required
import paho.mqtt.client as mclient
import Tools
import Tools.Config as conf
import Tools.Autodiscovery as ad
from Tools.Devices.Sensor import Sensor, SensorDeviceClasses
from Tools.Devices.BinarySensor import BinarySensor
from Tools.Devices.Switch import Switch
from Tools.Devices.Filters import DeltaFilter, TooHighFilter, MinTimeElapsed
from Tools.PluginManager import PluginManager

import logging
import os
import re
import schedule
import threading

import hashlib
try:
    from pyfingerprint.pyfingerprint import PyFingerprint
    from pyfingerprint.pyfingerprint import FINGERPRINT_CHARBUFFER1
except ImportError as ie: 
    try:
        import Tools.error as err
        err.try_install_package('pyfingerprint', throw=ie, ask=True)
    except err.RestartError:
        from pyfingerprint.pyfingerprint import PyFingerprint
        from pyfingerprint.pyfingerprint import FINGERPRINT_CHARBUFFER1

try:
    import gpiozero
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('gpiozero', throw=ie, ask=True)
    except err.RestartError:
        import gpiozero

from Tools import Pin


class PluginLoader: 

    @staticmethod
    def getConfigKey():
        return "GrowFingerprint"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return Fingerprint(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        FingerprintConfig(conf).run()


class Fingerprint:
    _shed_Job: Union[schedule.Job, None] = None
    _sensor: Sensor
    _plugin_manager: PluginManager
    err_str: str = "OK"
    _access_check: Union[threading.Thread, None] = None
    _access_check_stop: bool
    wakupPin: Union[Pin.Pin, None]

    currentFinger: BinarySensor
    currentError: BinarySensor


    level1: Switch
    level2: Switch
    level3: Switch

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        from gpiozero.pins.native import NativeFactory
        from gpiozero import Device
        Device.pin_factory = NativeFactory()

        self._config = conf.PluginConfig(opts, PluginLoader.getConfigKey())
        self.__client = client
        self.__logger = logger.getChild("Fingerprint")
        self._finger = PyFingerprint(
            self._config["serial"],
            57600,
            0xFFFFFFFF,
            self._config.get("password", 0x00000000)
            )
        
        if not self._finger.verifyPassword():
            self.err_str = "PASSWD"
        
        if self._config.get("WAKEUP", 0) is not 0:
            self.wakupPin = Pin.Pin(pin=self._config.get("WAKEUP", 0), direction=Pin.PinDirection.IN_PULL_LOW)
            self.wakupPin.set_detect(self.wakeup, Pin.PinEventEdge.BOTH)
        else:
            self.wakeup(None, threadsleep=False)
        

    def register(self):
        t = ad.Topics.get_std_devInf()

        self.currentFinger = BinarySensor(
            self.__logger,
            self._plugin_manager,
            self._config["name"],
            binary_sensor_type=ad.BinarySensorDeviceClasses.PRESENCE,
            value_template="{{ value_json.dedected }}",
            json_attributes=True,
            icon="mdi:fingerprint"
        )
        self.currentFinger.register()
        self.currentFinger.turn(
            {
                "dedected": False,
                "fingerID": -1,
                "confidency": 0,
                "hash": None
            }
        )
        self.currentError = BinarySensor(
            self.__logger,
            self._plugin_manager,
            "{} Error".format(self._config["name"]),
            ad.BinarySensorDeviceClasses.PROBLEM,
            json_attributes=True,
            value_template="{{ value_json.is_error }}"
        )
        self.currentError.register()
        self.update_error_sensor()

        self.level1 = Switch(
            self.__logger,
            self._plugin_manager,
            self.level1_callback,
            "{} Level1".format(self._config["name"]),
            icon="mdi:shield-lock"
        )
        self.level1.register()
        self.level1.turn(self._config.get("allow_level1", False))

        self.level2 = Switch(
            self.__logger,
            self._plugin_manager,
            self.level2_callback,
            "{} Level2".format(self._config["name"]),
            icon="mdi:shield-lock"
        )
        self.level2.register()
        self.level2.turn(self._config.get("allow_level2", False))

        self.level3 = Switch(
            self.__logger,
            self._plugin_manager,
            self.level3_callback,
            "{} Level3".format(self._config["name"]),
            icon="mdi:shield-lock"
        )
        self.level3.register()
        self.level3.turn(self._config.get("allow_level3", False))


    def level1_callback(self, message:str, state_requested=False):
        self._config["allow_level1"] = True if message == "ON" else False
        self.send_update()

    def level2_callback(self, message:str, state_requested=False):
        self._config["allow_level2"] = True if message == "ON" else False
        self.send_update()

    def level3_callback(self, message:str, state_requested=False):
        self._config["allow_level3"] = True if message == "ON" else False
        self.send_update()

    def update_error_sensor(self):
        try:
            self.currentFinger.turn(
                {
                    "is_error": self.err_str != "OK",
                    "msg": self.err_str
                }
            )
        except:pass

    def set_pluginManager(self, pm):
        self._plugin_manager = pm

    def stop(self):
        pass

    def sendStates(self):
        self.send_update(True)

    def send_update(self, force=False):
        # Send Error Messeges
        self.update_error_sensor()

        # if resend requested, null fingerprint
        if force:
            self.currentFinger.turn(
                {
                    "dedected": False,
                    "fingerID": -1,
                    "confidency": 0,
                    "hash": None
                }
            )
        
        # Update the Authorisation Levels to Home Assistant
        self.level1.turn(self._config.get("allow_level1", False))
        self.level2.turn(self._config.get("allow_level2", False))
        self.level3.turn(self._config.get("allow_level3", False))
    
    def access_thread(self):
        while not self._access_check_stop:
            try:
                img = self._finger.readImage()
                if not img:
                    sleep(0.1)
                    continue
                self._finger.convertImage(FINGERPRINT_CHARBUFFER1)
                res = self._finger.searchTemplate()
                
                optional = {}
                # Extra Exception handling, because this stuff is optional
                try:
                    if res[0] > -1:
                        self._finger.loadTemplate(res[0], FINGERPRINT_CHARBUFFER1)
                        characterics = str(self._finger.downloadCharacteristics(FINGERPRINT_CHARBUFFER1)).encode('utf-8')

                        optional = {
                            "sha256": hashlib.sha256(characterics).hexdigest(),
                            "capacity": self._finger.getStorageCapacity(),
                            "stored": self._finger.getTemplateCount(),
                            "security": self._finger.getSecurityLevel()
                        }

                except Exception as e:
                    self.err_str = str(e)
                    self.update_error_sensor()

                #Tell homeassistant about the new fingerprint
                required = {
                        "dedected": res[0] > -1,
                        "fingerID": res[0],
                        "confidency": res[1],
                        "hash": hex
                    }
                required.update(optional)
                self.currentFinger.turn( required )

                #Wait some time
                sleep( 5.0 if res[0] > -1 else 0.25 )

                #Clear the fingerprint message
                self.currentFinger.turn(
                    {
                        "dedected": False,
                        "fingerID": -1,
                        "confidency": 0,
                        "hash": None
                    }
                )

            except Exception as e:
                self.__logger.exception("access_thread()")
                self.err_str = str(e)
                self.update_error_sensor()

    def stop_access_thread(self):
        self._access_check_stop = True
        if self._access_check is not None:
            self._access_check.join()
            self._access_check = None
        if self._shed_Job is not None:
            schedule.cancel_job(self._shed_Job)
            self._shed_Job = None


    def wakeup(self, device, threadsleep:bool=True):
        if self._access_check is not None and self._access_check.is_alive():
            return

        if self._shed_Job is not None:
            schedule.cancel_job(self._shed_Job)
        if threadsleep:
            job = schedule.every(self._config.get("WAKEUP_active_secs", 120)).seconds
            job.do(self.stop_access_thread)
            self._shed_Job = job
        self._access_check_stop = False
        self._access_check = threading.Thread(target=self.access_thread, name="FingerAccess", daemon=False)
        self._access_check.start()


class FingerprintConfig:
    def __init__(self, conf: conf.BasicConfig):
        self.c = conf

    def run(self):
        from Tools import ConsoleInputTools as cit
        self.c["GrowFingerprint/name"] = cit.get_input("Unter welchem Namen soll der Fingerprint sensor bekannt sein. \n-> ", require_val=True, std_val="Fingerprint")
        self.c["GrowFingerprint/WAKEUP"] = cit.get_number_input("WAKEUP Pinnr:", 0)
        if self.c["GrowFingerprint/WAKEUP"] > 0:
            self.c["GrowFingerprint/WAKEUP_active_secs"] = cit.get_number_input("Sekunden die Aktiv auf Finger gewartet wird, nach einem WAKEUP?\n ->", 30)
        if cit.get_bool_input("Fingerprint Modul Passwort ändern? ", False):
            if cit.get_bool_input("Zufälliges Passwort erstellen?", False):
                import random
                sysr = random.SystemRandom()
                bits = sysr.getrandbits(32)
                self.c["GrowFingerprint/new_pw"] = bits
            else:
                self.c["GrowFingerprint/new_pw"] = cit.get_number_input("Bitte 32Bit Passwort eingeben: ", 0x00000000)

