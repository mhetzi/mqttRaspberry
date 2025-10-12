# -*- coding: utf-8 -*-
from abc import ABCMeta
import paho.mqtt.client as mclient

import json
import Tools.Config as conf
import logging
import subprocess

from Tools import PluginManager

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "ShellSwitch"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger):
        return ShellSwitch(opts, logger)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        ShellSwitchConf(conf).run()
    
    @staticmethod
    def getNeededPipModules() -> list[str]:
        return []


class ShellSwitch(PluginManager.PluginInterface):

    def __init__(self, opts: conf.BasicConfig, logger: logging.Logger):
        self._config = conf.PluginConfig(opts, "ShellSwitch")
        self.__logger = logger.getChild("ShellSwitch")
        self._registered_callback_topics = []
        self._name_topic_map = {}
        self._state_name_map = {}

    def disconnected(self):
        return super().disconnected()

    def exec_switch(self, name:str, on:bool, initKill=None, simulate=False):
        switch = self._config["entrys/{}".format(name)]
        state_js = {
            "on": switch.get("on_command", None),
            "off": switch.get("off_command", None)
        }
        try:
            if simulate:
                self._config["entrys/{}/wasOn".format(name)] = on =  on if switch.get("onOff", True) else False
                state_js["state"] = "OFF"
                state_js["error_code"] = 0
            elif initKill is None:
                if on:
                    cp = subprocess.run(switch.get("on_command", "False"), shell=True, check=True)
                    state_js["state"] = "ON" if switch.get("onOff", True) else "OFF"
                    state_js["error_code"] = cp.returncode
                    self.__logger.info("{} wurde angeschaltet.".format(name))
                else:
                    cp = subprocess.run(switch.get("off_command", "False"), shell=True, check=True)
                    state_js["state"] = "OFF"
                    state_js["error_code"] = cp.returncode
                    self.__logger.info("{} wurde ausgeschaltet.".format(name))
                self._config["entrys/{}/wasOn".format(name)] = on =  on if switch.get("onOff", True) else False
            elif initKill and switch["init_command"] is not None:
                self.__logger.info("Führe init command [{}] aus.".format(switch["init_command"]))
                cp = subprocess.run(switch["init_command"], shell=True, check=True)
            elif not initKill and switch["clean_command"] is not None:
                self.__logger.info("Führe clean command [{}] aus.".format(switch["clean_command"]))
                cp = subprocess.run(switch["clean_command"], shell=True, check=True)

        except subprocess.CalledProcessError as e:
            state_js["state"] = "OFF" if on else "ON"
            state_js["error_code"] = e.returncode
            self.__logger.error("ShellSwitch Rückgabewert der Shell ist nicht 0. Ausgabe der Shell: {}".format(e.output))
            switch["wasOn"] = not on if switch.get("onOff", True) else False
            state_js["state"] = state_js["state"] if switch.get("onOff", True) else "OFF"
        self._pluginManager._client.publish(self._state_name_map[name], json.dumps(state_js))

    def handle_switch(self, client, userdata, message: mclient.MQTTMessage):
        for topics in self._name_topic_map.keys():
            if message.topic == topics:
                self.__logger.debug("message.topic ({}) == topics({})".format(message.topic, topics))
                msg = message.payload.decode('utf-8')
                if msg == "ON":
                    self.__logger.debug("Schalte {} aufgrund der Payload {} an.".format(self._name_topic_map[topics], msg))
                    self.exec_switch(self._name_topic_map[topics], True)
                elif msg == "OFF":
                    self.exec_switch(self._name_topic_map[topics], False)
                    self.__logger.debug("Schalte {} aufgrund der Payload {} aus.".format(self._name_topic_map[topics], msg))
                else:
                    self.__logger.error("Payload ({}) ist nicht richtig!".format(msg))
            else:
                self.__logger.debug("message.topic ({}) != topics({})".format(message.topic, topics))

    def register(self, wasConnected=False):
        self._config.get("reg_config_topics", [])
        if self._config.get("dereg", False):
            for command_topic in self._config.get("reg_config_topics", []):
                self._pluginManager._client.publish(command_topic, "", retain=False)
            self._config["reg_config_topics"] = []
            self._config["dereg"] = False

        for name in self._config.get("entrys", {}).keys():
            self.__logger.info("Erstelle MQTT zeugs für {}...".format(name))
            friendly_name = self._config["entrys"][name]["name"]
            uid = "switch.ShSw-{}.{}".format(conf.autodisc.Topics.get_std_devInf().pi_serial, name)
            topics = self._config.get_autodiscovery_topic(conf.autodisc.Component.SWITCH, name, conf.autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            conf_payload = topics.get_config_payload(friendly_name, "", None, value_template="{{ value_json.state }}", json_attributes=["on", "off", "error_code"], unique_id=uid)
            self.__logger.debug("Veröffentliche Config Payload {} in Topic {}".format(topics.config, conf_payload))
            self._pluginManager._client.publish(topics.config, conf_payload, retain=True)
            self._pluginManager._client.subscribe(topics.command)
            self._pluginManager._client.message_callback_add(topics.command, self.handle_switch)
            if topics.config not in self._config["reg_config_topics"]:
                self._config["reg_config_topics"].append(topics.config)
            self._registered_callback_topics.append(topics.command)
            self._name_topic_map[topics.command] = name
            self._state_name_map[name] = topics.state
            self.exec_switch(name, False, True)
            if not self._config["entrys"][name].get("onOff", True):
                self.exec_switch(name, False)
            if self._config["entrys"][name].get("setOnLoad", True):
                self.exec_switch(name, self._config["entrys"][name]["wasOn"])

    def stop(self):
        for name in self._config.get("entrys", {}).keys():
            self.exec_switch(name, False, False)

        for reg in self._registered_callback_topics:
            self._pluginManager._client.message_callback_remove(reg)

    def sendStates(self):
        for name in self._config.get("entrys", {}).keys():
            if self._config["entrys"][name].get("setOnLoad", True):
                self.exec_switch(name, self._config["entrys"][name]["wasOn"], simulate=True)

    def set_pluginManager(self, pm):
        pass

class ShellSwitchConf:
    def __init__(self, opts: conf.BasicConfig):
        self.c = conf.PluginConfig(opts, "ShellSwitch")
        self.c.get("entrys", {})

    def run(self):
        from Tools import ConsoleInputTools
        while True:
            action = ConsoleInputTools.get_number_input("Was möchtest du tun?\n 1) Neuen anlegen\n 2)Einen löschen\n 3) Beenden\n ", 3)
            if action != 1 and action != 2 and action != 3:
                print("Nee war keine gültige eingabe.")
                continue
            elif action == 2:
                print("Diese ShellSwitche stehen zur auswahl.\n 0) Nichts löschen.")
                indicies = {}
                index = 1
                for name in self.c.get("entrys", {}).keys():
                    print("{}) {}\n   On: \"{}\" Off: \"{}\"".format(index, name,
                                                                     self.c.get("entrys/{}/on_command".format(name), ""),
                                                                     self.c.get("entrys/{}/off_command".format(name))))
                    indicies[index] = name

                toDelete = ConsoleInputTools.get_number_input("Bitte die Nummer eingeben.", 0)
                if toDelete == 0:
                    continue
                else:
                    if indicies.get(toDelete, None) is None:
                        print("Fehler! Zahl ungültig.")
                    else:
                        del self.c["entrys/{}/off_command".format(indicies[toDelete])]

            elif action == 1:
                entry = {"wasOn": False}
                onOff = ConsoleInputTools.get_bool_input("Welcher Modus soll angewendet werden? Ein/Aus (J) oder Pulse (N)", True)
                entry["init_command"] = ConsoleInputTools.get_input("Kommando beim initialisieren?: ")
                entry["clean_command"] = ConsoleInputTools.get_input("Kommando beim beenden?: ")
                entry["onOff"] = onOff
                if onOff:
                    entry["on_command"] = ConsoleInputTools.get_input("Kommando beim Einschalten?: ")
                    entry["off_command"] = ConsoleInputTools.get_input("Kommando beim Ausschalten?: ")
                else:
                    entry["on_command"] = ConsoleInputTools.get_input("Kommando beim Pulsieren?: ")
                entry["setOnLoad"] = ConsoleInputTools.get_bool_input("Status beim Starten wiederherstellen?")
                entry["name"] = ConsoleInputTools.get_input("Name des Switches?")
                entry["icon"] = ConsoleInputTools.get_input("Welches icon soll gesendet werden? (z.B.: mdi:lightbulb")
                entry["broadcast"] = ConsoleInputTools.get_bool_input("Soll der Switch in HomeAssistant gefunden werden?", True)
                self.c["entrys"][entry["name"].replace(" ","")] = entry
            elif action == 3:
                break
        self.c["dereg"] = True
