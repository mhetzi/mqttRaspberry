# -*- coding: utf-8 -*-

from Mods.victron.github.vedirect.vedirect import Vedirect
import Mods.victron.Constants as CONST

from Tools.Autodiscovery import DeviceInfo
from Tools.Config import PluginConfig

import threading
import serial
from time import sleep
from logging import Logger

class Connection(threading.Thread):
    _ved: Vedirect

    def _device_ready_call(self):
        self._log.error("_device_ready_call not overriden")
        pass

    def __init__(self, config: PluginConfig, log:Logger):
        threading.Thread.__init__(self)
        self.__serial_port = config.get("serial", "/dev/ttyAMA0")
        self._log = log.getChild("Connection")

        self._device = DeviceInfo()
        self._device.model = None
        self._device_ready = False
        self._shutdown = False
        self._ved = None
        self._calls = {}

        self.name = "VE.Direct Serial"

    def set_callbacks(self, callbacks: dict):
        self._log.debug("Callbacks set!")
        self._calls = callbacks
    
    def run(self):
        self._log.info("Starte VE.Direct verbindung...")
        while not self._shutdown:
            try:
                self._log.info("Benutze Serial Port {}.".format(self.__serial_port))
                self._ved = Vedirect(self.__serial_port, 1000)
                self._log.info("VE.Direct wird gelesen... (forever)")
                self._ved.read_data_callback(self.veCallback)
            except serial.SerialException:
                self._ved = None
                self._log.exception("Ve.Direct verbindung abgebrochen")
                sleep(5000)

    def stop(self):
        self._shutdown = True
        if self._ved is not None:
            self._ved.ser.close()

    def veCallback(self, data: dict):
        self._log.debug("Processing: {} ...".format(data))
        for key, value in data.items():
            if self._device_ready:
                f = self._calls.get(key, None)
                if callable(f): f(value)
                elif len(self._calls) < 1:
                    self._log.warning("No callable list")
                    self._device_ready = False
            elif key == "PID":
                self._device.model = CONST.PIDs.get(value, None)
                if self._device.model is None:
                    swapped_dict = dict({(y, x) for x, y in CONST.PIDs.items()})
                    self._device.model = swapped_dict.get(value, None)
                    if self._device.model is None:
                        self._device.model = "Unknown"
                        self._log.error("Konnte Model {} nicht finden.".format(value))
            elif key == "FW":
                self._device.sw_version = value
            elif key == "SER#":
                self._device.IDs.append(value)
                self._device_ready = True
                if callable(self._device_ready_call):
                    self._device_ready_call()
                else:
                    self._log.error("self._device_ready_call is not callable!")
            else:
                if self._device.model is not None and self._device.sw_version != "" and len(self._device.IDs) > 0:
                    self._log.info("Geräteinformationen gesammelt! Gerät bereit.")
                    self._device_ready = True
                    self._device.mfr = "Victron"
                    if callable(self._device_ready_call):
                        self._device_ready_call()
                    else:
                        self._log.error("self._device_ready_call is not callable!")
                else:
                    self._log.debug("{}: {}".format(key, value))
    
