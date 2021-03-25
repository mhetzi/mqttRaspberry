# -*- coding: utf-8 -*-

import ctypes
import json
from Tools.Autodiscovery import BinarySensorDeviceClasses, SensorDeviceClasses
from time import sleep
from typing import Tuple, Union
from Tools.Config import PluginConfig
from Tools.PluginManager import PluginManager
from Tools.Devices import BinarySensor, Sensor, Switch
from Tools.Devices.Filters import DeltaFilter

from logging import Logger
from threading import Thread

import pystray
from PIL import Image, ImageDraw

import win32con
import win32api

class Colors(tuple):
    def __str__(self):
        return ' and '.join(self)

class DeviceMenuItem(pystray.MenuItem):
    _confirm = False
    
    def doConfirm(self):
        if self._confirm:
            yesno = win32api.MessageBox(0, "Möchtest du die Aktion {} wirklich ausführen".format(self.text), "Aktion ausführen?", win32con.MB_YESNO | win32con.MB_ICONQUESTION | win32con.MB_TOPMOST)
            if yesno == win32con.IDNO:
                return True
        return False

class SensorDeviceItem(DeviceMenuItem):

    def device_action(self):

        if self.doConfirm():
            return

        self._sensor.turnOn()
        sleep(1)
        self._sensor.turnOff()

    def __init__(self, name, sensor: BinarySensor.BinarySensor, confirm=False):
        self._sensor = sensor
        self._confirm = confirm
        super().__init__(name, action=self.device_action)

class SwitchDeviceItem(DeviceMenuItem):
    
    def device_action(self):
        if self.doConfirm():
            return
        self._config["itemList/{}/wasOn".format(self.text)] = self._checked

        if self.checked:
            self._switch.turnOn()
            return
        self._switch.turnOff()
    
    def device_callback(self, state_requested=True, message=None):
        if state_requested:
            self.device_action()
        if message is not None:
            message = message.payload.decode('utf-8')
            self._checked = message == "ON"
            self._config["itemList/{}/wasOn".format(self.text)] = self._checked

    def __init__(self, name, isOn, config: PluginConfig, logger:Logger, pman: PluginManager, measurement_unit: str='', ava_topic=None, value_template=None, json_attributes=False, device=None, unique_id=None, icon=None):
        self._switch = Switch.Switch(
            logger, pman=pman, callback=self.device_callback, name=name, measurement_unit=measurement_unit, ava_topic=ava_topic, value_template=value_template, json_attributes=json_attributes,
            device=device, unique_id=unique_id
        )
        self._switch.register()
        self._config = config
        super().__init__(name, action=self.device_action, checked=isOn)


class win32Systray:
    _shutdown = False
    _icon_rdy = False
    _pman: PluginManager = None

    _menuItemsInit: list[pystray.MenuItem] = []
    _menuItemsDynamic: list[pystray.MenuItem] = []


    def image(self, width=64, height=64) -> tuple[Image.Image, Colors]:
        """Generates an icon image.
        :return: the tuple ``(image, colors)``, where  ``image`` is a
            *PIL* image and ``colors`` is a tuple containing the colours as
            *PIL* colour names, suitable for printing; the stringification of
            the tuple is also suitable for printing
        """

        colors = Colors(("blue", "white"))
        img = Image.new('RGB', (width, height), colors[0])
        dc = ImageDraw.Draw(img)

        dc.rectangle((width // 2, 0, width, height // 2), fill=colors[1])
        dc.rectangle((0, height // 2, width // 2, height), fill=colors[0])

        return img, colors


    def icon_created(self, icon):
        self._icon_rdy = True
        self._sicon.visible = True
        self._log.info("Systray Icon wird jetzt angezeigt.")

    def killPluginManager(self):
        if self._pman is not None:
            self._pman.shutdown()
        self._sicon.notify("Interner Fehler (PluginManager nicht gesetzt), kann nicht normal beendet werden. Versuche exit()")
        exit(1)
        
    def sicon_thread(self):
        self._log.debug("Icon image wird gezeichnet...")
        img, colors = self.image()

        self._log.debug("Erstelle initales Menü...")
        items:list[pystray.MenuItem] = []
        items.append(pystray.MenuItem("Warte auf verbindung...",None))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("Beenden", self.killPluginManager))
        self._menuItemsInit = tuple(items)

        self._menu = pystray.Menu(*items)

        self._log.debug("Beginne mit dem mainloop von pysystray...")
        self._sicon = pystray.Icon("mqttScripts", icon=img, menu=self._menu)
        self._sicon.run(setup=self.icon_created)

    def __init__(self, config: PluginConfig, log: Logger) -> None:
        self._config = PluginConfig(config, "systray")
        self._log = log.getChild("STRAY")

        self.icon_thread = Thread(name="systray", daemon=False, target=self.sicon_thread)
        self.icon_thread.start()

    @staticmethod
    def getNewDeviceEntry():
        from Tools import ConsoleInputTools
        config = {}
        name = ConsoleInputTools.get_input("Name für den Eintrag?")
        config["type"] = "switch" if ConsoleInputTools.get_bool_input("Soll der eintrag als Schalter fungieren?", False) else "action"
        config["confirm"] = ConsoleInputTools.get_bool_input("Auswählen des Eintrages bestätigen?", False)

        return name, config

    def generateDeviceIems(self):
        citems: dict = self._config.get("itemList", {})
        mitems: list[pystray.MenuItem] = []
        for name, entry in citems.items():
            ctype = entry.get("type", "action")
            if ctype == "action":
                bsensor = BinarySensor.BinarySensor(
                    self._log, self._pman, name, BinarySensorDeviceClasses.GENERIC_SENSOR
                )
                bs = SensorDeviceItem(
                    name, bsensor, confirm=entry.get("confirm", False)
                )
                bsensor.register()
                mitems.append(bs)
            elif ctype == "switch":
                sw = SwitchDeviceItem(
                    name, entry.get("wasOn", False), self._config, self._log, self._pman
                )
                sw._confirm = entry.get("confirm", False)
                mitems.append(sw)
        mitems.append(pystray.Menu.SEPARATOR)
        mitems.append(pystray.MenuItem("Beenden", self.killPluginManager))
        self._menu = pystray.Menu(*mitems)
        self._sicon.menu = self._menu
        self._menuItemsDynamic = mitems

    def updateDeviceItems(self):
        for mis in self._menuItemsDynamic:
            if isinstance(mis, SwitchDeviceItem):
                sdi: SwitchDeviceItem = mis
                sdi.device_action()

    def register(self, wasConnected: bool, pman: PluginManager):
        self._pman = pman
        if self._icon_rdy:
            self._sicon.notify("Verbindung mit MQTT Broker {}hergestellt".format("wieder" if wasConnected else ""))

        self.generateDeviceIems()
        
    def sendUpdate(self, force=True):
        if force:
            self.updateDeviceItems()

    def disconnected(self):
        self._menu.items = self._menuItemsInit
        self._sicon.notify("Verbindung zum MQTT Server unterbrochen!")
    
    def shutdown(self):
        self._shutdown = True
        if self._icon_rdy:
            self._sicon.stop()
        