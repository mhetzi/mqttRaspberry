# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import logging
from Tools.Config import BasicConfig, PluginConfig 
from Tools import ConsoleInputTools

from Mods.CoE import getConfigKey

class CoEConfigurator:

    def __init__(self):
        pass

    def configure(self, master_config: BasicConfig):
        config = PluginConfig(master_config, getConfigKey())

        if config.get("CMIs", None) is None:
            config["CMIs"] = {}
        
        while True:
            action = ConsoleInputTools.get_number_input("Drücke 1 zum entfernen, 2 zum hinzufügen, 3 zum bearbeiten, 0 zum beenden", 0)
            if action == 0:
                break
            edit_cmi = None
            if action == 1 or action == 3:
                print("Folgende CMIs wurden hinzugefügt:")
                for idx in range(0, len(config["CMIs"].keys())):
                    print(f" {idx+1}: {list(config['CMIs'].keys())[idx]}")
                nr: int = ConsoleInputTools.get_number_input("Welche Nr. soll entfernt werden?", int(0))
                if nr == 0 or nr > len(config["CMIs"].keys()):
                    continue
                edit_cmi = list(config["CMIs"].keys())[nr-1]
                if action == 3:
                    action = 2
                else:
                    del config["CMIs"][edit_cmi]
                    continue
            if action == 2:
                if edit_cmi is None:
                    edit_cmi = ConsoleInputTools.get_input("IP Addresse des CMI: ")
                    config["CMIs"][edit_cmi] = {"switches": []}
                if ConsoleInputTools.get_bool_input("Schalter bearbeiten? ", False):
                    print("Folgende Schalter wurden hinzugefügt: ")
                    for idx in range(0, len(config["CMIs"][edit_cmi]["switches"])):
                        print(f" {idx+1}: {config['CMIs'][edit_cmi]['switches'][idx]['name']}")
                    nr: int = ConsoleInputTools.get_number_input("Welche Nr. soll entfernt werden? 0 für keiner. ", int(0))
                    if nr > 0 and nr <= len(config["CMIs"][edit_cmi]["switches"]):
                        del config["CMIs"][edit_cmi]["switches"][nr-1]
                        continue
                    name = ConsoleInputTools.get_input("Welcher Name soll der Schalter bekommen? ", False, None)
                    node = ConsoleInputTools.get_number_input("Auf welche CAN Node ID soll der Schalter senden? ")
                    channel = ConsoleInputTools.get_number_input("Auf welchen Netzwerkausgang soll der Schalter senden? ")
                        #s["name"], cmi, s["node"], s["channel"]
                    s = {"name": name, "node": node, "channel": channel-1, "last": False}
                    config["CMIs"][edit_cmi]["switches"].append(s)
                    config.markFileAsDirty()


        dereg = ConsoleInputTools.get_bool_input("Remove existing from MQTT Autodiscovery?", False)

        if dereg:
            config["deregister"] = dereg
            print("Beim nächsten normalen Start wird alles deregestriert!")