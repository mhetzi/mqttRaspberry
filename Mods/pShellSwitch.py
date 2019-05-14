# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient

import json
import Tools.Config as conf
import logging
import subprocess

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "ShellSwitch"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return ShellSwitch(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        ShellSwitchConf(conf).run()


class ShellSwitch:

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self._config = opts
        self.__client = client
        self.__logger = logger.getChild("ShellSwitch")
        self.__ava_topic = device_id
        self._registered_callback_topics = []
        self._name_topic_map = {}
        self._state_name_map = {}

    def exec_switch(self, name:str, on:bool, initKill=None):
        switch = self._config["ShellSwitch/entrys/{}".format(name)]
        state_js = {"on": switch["on_command"], "off": switch["off_command"]}
        try:
            if initKill is None:
                if on:
                    cp = subprocess.run(switch["on_command"], shell=True, check=True)
                    self._config["ShellSwitch/entrys/{}/wasOn".format(name)] = on
                    state_js["state"] = "ON"
                    state_js["error_code"] = cp.returncode
                    self.__logger.info("{} wurde angeschaltet.".format(name))
                else:
                    cp = subprocess.run(switch["off_command"], shell=True, check=True)
                    self._config["ShellSwitch/entrys/{}/wasOn".format(name)] = on
                    state_js["state"] = "OFF"
                    state_js["error_code"] = cp.returncode
                    self.__logger.info("{} wurde ausgeschaltet.".format(name))
                switch["wasOn"] = on
            elif initKill and switch["init_command"] is not None:
                cp = subprocess.run(switch["init_command"], shell=True, check=True)
            elif not initKill and switch["clean_command"] is not None:
                cp = subprocess.run(switch["clean_command"], shell=True, check=True)

        except subprocess.CalledProcessError as e:
            state_js["state"] = "OFF" if on else "ON"
            state_js["error_code"] = e.returncode
            self.__logger.error("ShellSwitch Rückgabewert der Shell ist nicht 0. Ausgabe der Shell: {}".format(e.output))
            switch["wasOn"] = not on
        self.__client.publish(self._state_name_map[name], json.dumps(state_js))

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

    def register(self):
        self._config.get("ShellSwitch/reg_config_topics", [])
        if self._config.get("ShellSwitch/dereg", False):
            for command_topic in self._config.get("ShellSwitch/reg_config_topics", []):
                self.__client.publish(command_topic, "", retain=False)
            self._config["ShellSwitch/reg_config_topics"] = []
            self._config["ShellSwitch/dereg"] = False

        ava_topic = self._config.get_autodiscovery_topic(conf.autodisc.Component.SWITCH, "availibility_switch", conf.autodisc.DeviceClass()).ava_topic
        self.__client.will_set(ava_topic, "offline", retain=True)
        self.__client.publish(ava_topic, "online", retain=True)

        for name in self._config.get("ShellSwitch/entrys", {}).keys():
            self.__logger.info("Erstelle MQTT zeugs für {}...".format(name))
            friendly_name = self._config["ShellSwitch/entrys"][name]["name"]
            uid = "switch.ShSw-{}.{}".format(conf.autodisc.Topics.get_std_devInf().pi_serial, name)
            topics = self._config.get_autodiscovery_topic(conf.autodisc.Component.SWITCH, name, conf.autodisc.SensorDeviceClasses.GENERIC_SENSOR)
            conf_payload = topics.get_config_payload(friendly_name, "", ava_topic, value_template="{{ value_json.state }}", json_attributes=["on", "off", "error_code"], unique_id=uid)
            self.__logger.debug("Veröffentliche Config Payload {} in Topic {}".format(topics.config, conf_payload))
            self.__client.publish(topics.config, conf_payload, retain=True)
            self.__client.subscribe(topics.command)
            self.__client.message_callback_add(topics.command, self.handle_switch)
            if topics.config not in self._config["ShellSwitch/reg_config_topics"]:
                self._config["ShellSwitch/reg_config_topics"].append(topics.config)
            self._registered_callback_topics.append(topics.command)
            self._name_topic_map[topics.command] = name
            self._state_name_map[name] = topics.state
            self.exec_switch(name, False, True)
            self.exec_switch(name, self._config["ShellSwitch/entrys"][name]["wasOn"])

    def stop(self):
        for name in self._config.get("ShellSwitch/entrys", {}).keys():
            self.exec_switch(name, False, False)

        for reg in self._registered_callback_topics:
            self.__client.message_callback_remove(reg)

    def sendStates(self):
        for name in self._config.get("ShellSwitch/entrys", {}).keys():
            self.exec_switch(name, self._config["ShellSwitch/entrys"][name]["wasOn"])


class ShellSwitchConf:
    def __init__(self, conf: conf.BasicConfig):
        self.c = conf
        self.c.get("ShellSwitch/entrys", {})

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
                for name in self.c.get("ShellSwitch/entrys", {}).keys():
                    print("{}) {}\n   On: \"{}\" Off: \"{}\"".format(index, name,
                                                                     self.c.get("ShellSwitch/entrys/{}/on_command".format(name), ""),
                                                                     self.c.get("ShellSwitch/entrys/{}/off_command".format(name))))
                    indicies[index] = name

                toDelete = ConsoleInputTools.get_number_input("Bitte die Nummer eingeben.", 0)
                if toDelete == 0:
                    continue
                else:
                    if indicies.get(toDelete, None) is None:
                        print("Fehler! Zahl ungültig.")
                    else:
                        del self.c["ShellSwitch/entrys/{}/off_command".format(indicies[toDelete])]

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
                entry["name"] = ConsoleInputTools.get_input("Name des Switches?")
                entry["icon"] = ConsoleInputTools.get_input("Welches icon soll gesendet werden? (z.B.: mdi:lightbulb")
                entry["broadcast"] = ConsoleInputTools.get_bool_input("Soll der Switch in HomeAssistant gefunden werden?", True)
                self.c["ShellSwitch/entrys"][entry["name"].replace(" ","")] = entry
            elif action == 3:
                break
        self.c["ShellSwitch/dereg"] = True
