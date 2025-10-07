
from typing import IO, Union
from paho.mqtt.client import Client as MqttClient
import Tools.Config as conf
import Tools.Autodiscovery as autodisc
import Tools.PluginManager as PluginMan
from Tools.Devices.Lock import Switch, Lock, LockState
from Tools.Devices.BinarySensor import BinarySensor
import logging
import schedule
import os

from time import sleep

class PluginLoader(PluginMan.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "QMK_VIA"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        try:
            import hid
        except ImportError as ie:
            import Tools.error as err
            err.try_install_package('hid', throw=ie, ask=False)
        import Mods.qmk_via.Plugin as Plugin
        return Plugin.ViaPlugin(conf.PluginConfig(opts, PluginLoader.getConfigKey()), logger.getChild(PluginLoader.getConfigKey()), device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        ViaConfig().configure(conf, logger.getChild(PluginLoader.getConfigKey()))

    @staticmethod
    def getNeededPipModules() -> list[str]:
        try:
            import hid
        except ImportError as ie:
            return ["hid"]
        return []



class ViaConfig:
    def __init__(self):
        pass

    def configure(self, conff: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        import json
        con = conf.PluginConfig(conff, PluginLoader.getConfigKey())
        keyboards: list[dict] = con.get("keyboards", []) # pyright: ignore[reportAssignmentType]
        if not isinstance(keyboards, list):
            con["keyboards"] = []
            keyboards = con["keyboards"]
        while True:
            keyboards = con.get("keyboards", []) # pyright: ignore[reportAssignmentType]
            action = ConsoleInputTools.get_number_input("Drücke 1 zum entfernen, 2 zum hinzufügen, 0 zum beenden", 0)
            if action == 0:
                break
            edit_keyboard = None
            if action == 1 or action == 3:
                print("Folgende Keyboards wurden hinzugefügt:")
                for idx in range(0, len(keyboards)):
                    print(f" {idx+1}: {keyboards[idx].get('fname', f'{keyboards[idx].get('vid', 0)}_{keyboards[idx].get('pid', 0)}')}")
                nr: int = ConsoleInputTools.get_number_input(f"Welche Nr. soll { 'entfernt' if nr == 1 else 'bearbeitet' } werden?", int(0)) # pyright: ignore[reportArgumentType]
                if nr == 0 or nr > len(keyboards):
                    continue
                edit_keyboard = keyboards[nr-1]
                if action == 3:
                    action = 2
                else:
                    del con[f"keyboards/{nr-1}"]
                    con.markFileAsDirty()
                    continue
            if action == 2:
                if edit_keyboard is None:
                    vid = ConsoleInputTools.get_number_input("VID des Keyboards (Hex mit 0x oder Dezimal): ", 0)
                    pid = ConsoleInputTools.get_number_input("PID des Keyboards (Hex mit 0x oder Dezimal): ", 0)
                    if vid == 0 or pid == 0:
                        print("VID und PID müssen gesetzt sein!")
                        continue
                    fname = ConsoleInputTools.get_input("Freundlicher Name des Keyboards: ", False, f"QMK_VIA:{vid}_{pid}")
                    js_file = ConsoleInputTools.get_input("Pfad zur VIA JSON Datei (leer für eingebettet): ", True, None)
                    js_embedded = None
                    if js_file is None or not os.path.isfile(js_file):
                        if ConsoleInputTools.get_bool_input("Soll die VIA JSON Datei eingebettet werden? ", True):
                            js_embedded_str = ConsoleInputTools.get_input("Füge den Inhalt der VIA JSON Datei ein (mehrzeilig, Ende mit leerer Zeile):\n", False, None, multiline=True)
                            try:
                                js_embedded = json.loads(js_embedded_str)
                            except Exception as e:
                                logger.error(f"Fehler beim Parsen der VIA JSON Datei: {e}")
                                js_embedded = None
                    keyboard = {
                        "vid": vid,
                        "pid": pid,
                        "fname": fname,
                        "jsstr": js_file if js_file is not None and os.path.isfile(js_file) else None,
                        "embedded": js_embedded
                    }
                    keyboards.append(keyboard)
                    edit_keyboard = None