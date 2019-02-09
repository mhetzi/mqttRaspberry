# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import logging
import Tools.Config as tc
from Tools import ConsoleInputTools


class WeatherflowConfigurator:

    def __init__(self):
        pass

    def configure(self, config: tc.BasicConfig):
        host = ConsoleInputTools.get_input("Broadcast Addresse: ", std_val="255.255.255.255")
        port = ConsoleInputTools.get_number_input("Port: ", 50222)
        events = ConsoleInputTools.get_bool_input("Wetter events senden? ", True)
        dereg = ConsoleInputTools.get_bool_input("Remove existing from MQTT Autodiscovery?", False)

        config["Weatherflow/broadcast_addr"] = host
        config["Weatherflow/broadcast_port"] = port
        config["Weatherflow/events"] = events

        if dereg:
            config["Weatherflow/deregister"] = dereg
            print("Beim nächsten normalen Start wird alles deregestriert!")