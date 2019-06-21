# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient

import Tools.Config as conf
import logging
import os
import errno
import json

import Mods.PiCameraMotion as pcm
import Mods.PiCameraMotion.Main as pcma

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "PiMotion"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        plugin = pcma.PiMotionMain(client, opts, logger, device_id)
        return plugin

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        conf["PiMotion/camera/width"] = ConsoleInputTools.get_number_input("Resolution width ", 640)
        conf["PiMotion/camera/height"] = ConsoleInputTools.get_number_input("Resolution height ", 480)
        conf["PiMotion/camera/fps"] = ConsoleInputTools.get_number_input("Framerate ", 25)
        comf["PiMotion/camera/denoise"] = ConsoleInputTools.get_bool_input("Denoise Video? ")
        print("")
        conf["PiMotion/motion/recordPre"] = ConsoleInputTools.get_number_input("Sekunden vor Bwegung aufnehmen ", 1)
        conf["PiMotion/motion/recordPost"] = ConsoleInputTools.get_number_input("Sekunden nach Bwegung aufnehmen ", 1)
        print()
        conf["PiMotion/motion/sensorName"] = ConsoleInputTools.get_input("Bewegungsmelder Name ")
        conf["PiMotion/motion/motion_frames"] = ConsoleInputTools.get_number_input("Frames bis Bewegung gemeldet wird ")
        conf["PiMotion/motion/still_frames"] = ConsoleInputTools.get_number_input("Frames bis keine Bewegung mehr gemeldet wird ")
        conf["PiMotion/motion/minNoise"] = ConsoleInputTools.get_number_input("Mindestens diesen Noise Wert ereichen ")
        print()
        conf["PiMotion/rtsp/enabled"] = ConsoleInputTools.get_bool_input("RTSP Server aktivieren? ")
        conf["PiMotion/http/enabled"] = ConsoleInputTools.get_bool_input("HTTP Server aktivieren? ")
        

# WebSocket HotBlock Streming machen

# HotBlock deadblock
#   -> analysers.py HotBlock Ausblendungsmaske überlagern
#   -> HTTP Ausblednungsmaske bearbeiten

# #HotBlock Regionen
#   -> analysers.py Regionenfilter
#   -> HTTP Regionenfilter bearbeiten

# ^-> Bewegungsrichtung in Region ( UP, DOWN, LEFT, RIGHT)
#    -> analysers.py Regionenfilter ausbauen
#    -> HTTP Reginenfilter Editor ausbauen

# MQTT
#   -> Bewegungsmelder (BinarySensor, evtl. Attribute HotestBlock)
#   -> Zonenbewegungsmelder (wie oben + bewegungsrichtungs attribut)