# -*- coding: utf-8 -*-
from Tools import ConsoleInputTools
from Tools import PluginManager
from Tools.Config import PluginConfig

import paho.mqtt.client as mclient
import Tools.Config as conf
import logging

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "kaifa_smart_meter"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        from Mods.kaifa.Main import KaifaPlugin as pl
        return pl(client, PluginConfig(opts, PluginLoader.getConfigKey()), logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        KaifaPluginConfig(conf).run()

    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import serial
        except ImportError as ie:
            return ["pyserial"]
        return []


class KaifaPluginConfig(PluginManager.PluginInterface):
    def __init__(self, conf: conf.BasicConfig):
        self.c = PluginConfig(conf, PluginLoader.getConfigKey())
        meters = self.c.get("meter", default=None)
        if not isinstance(meters, list):
            meters = []
            self.c["meters"] = []
        self.currIndex = len(meters) - 1

    def addSmartMeter(self):
        meter = {}
        meter["port"] = ConsoleInputTools.get_input("Serielle Schnittstelle", require_val=True)
        meter["baudrate"] = ConsoleInputTools.get_number_input("Baudrate", map_no_input_to=2400)
        meter["parity"] = ConsoleInputTools.get_input("Parity", require_val=False, std_val="serial.PARITY_NONE")
        meter["stopbits"] = ConsoleInputTools.get_input("Stopbits", std_val="serial.STOPBITS_ONE")
        meter["bytesize"] = ConsoleInputTools.get_input("Bytesize", std_val="serial.EIGHTBITS")
        meter["key_hex_string"] = ConsoleInputTools.get_input("Entschlüsselungskey", require_val=True)
        meter["interval"] = ConsoleInputTools.get_number_input("Interval (Nicht mehr als 5)", map_no_input_to=1)
        meter["supplier"] = ConsoleInputTools.get_input("Netz Betreiber", std_val="EVN")
        self.c["meters"].append(meter)
        self.currIndex += 1
        
    def remSmartMeter(self):
        print("Auflistung aller Seriellen Ports:")
        print("0 um zu beenden.")
        for index in len(self.c["meter"]):
            port = self.c[f"meter/{index}"]
            print(f"{index+1}. {port}")
        
        toDelete = ConsoleInputTools.get_number_input("Nummer wählen", map_no_input_to=0)
        if toDelete == 0:
            return
        toDelete -= 0
        del self.c[f"meter/{toDelete}"]


    def run(self):
        while True:
            print("Mögliche Aktionen: \n 1. Smart Meter hinzufügen | 2. Smart Meter löschen\n 0. Beenden")
            action = ConsoleInputTools.get_number_input("Aktion", "0")
            match action:
                case 0: return
                case 1: self.addSmartMeter()
                case 2: self.remSmartMeter()
                case _: print("Ungültige Auswahl")

