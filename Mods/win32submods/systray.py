# -*- coding: utf-8 -*-

from Tools.Autodiscovery import BinarySensorDeviceClasses, SensorDeviceClasses
from time import sleep
from typing import Tuple, Union
from Tools.Config import PluginConfig
from Tools.PluginManager import PluginManager
from Tools.Devices import BinarySensor, Sensor
from Tools.Devices.Filters import DeltaFilter

from logging import Logger
from threading import Thread

import pystray
from PIL import Image, ImageDraw

class Colors(tuple):
    def __str__(self):
        return ' and '.join(self)

class win32Systray:
    _shutdown = False
    _icon_rdy = False
    _pman: PluginManager = None


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

    def icon_created(self):
        self._icon_rdy = True

    def killPluginManager(self):
        if self._pman is not None:
            self._pman.shutdown()
        self._sicon.notify("Interner Fehler (PluginManager nicht gesetzt), kann nicht normal beendet werden. Versuche exit()")
        exit(1)
        

    def __init__(self, config: PluginConfig, log: Logger) -> None:
        self._config = PluginConfig(config, "systray")
        self._log = log.getChild("STRAY")
        img, colors = self.image()

        items:list[pystray.MenuItem] = []
        items.append(pystray.MenuItem("Beenden", self.killPluginManager))


        menu = pystray.Menu(items=items)

        self._sicon = pystray.Icon("mqttScripts", icon=img, menu=menu)

        self.icon_thread = Thread(name="systray", daemon=False, target=lambda: self._sicon.run(setup=self.icon_created))
        self.icon_thread.start()



    def register(self, wasConnected: bool, pman: PluginManager):
        self._pman = pman
        if self._icon_rdy:
            self._sicon.notify("Verbindung mit MQTT Broker {}hergestellt".format("wieder" if wasConnected else ""))

    def sendUpdate(self, force=True):
        pass
    
    def shutdown(self):
        self._shutdown = True
        if self._icon_rdy:
            self._sicon.stop()
        