# -*- coding: utf-8 -*-

import logging
import enum
import json

import gpiozero
import paho.mqtt.client as mclient
import schedule

import Tools.Config as conf

# Platine Belegung
# Taster Pin_22 GPIO_25
#
# Reed_1 Pin_16 GPIO_23
# Reed_2 Pin_18 GPIO_24
# Reed_3 Pin_15 GPIO_22

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "rpiDoor"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return DoorOpener(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        print("Pins standartmäßig nach BCM schema (gpiozero angaben gestattet)")

        conf["rpiDoor/unlockPin"] = ConsoleInputTools.get_input("Pinnummer der entsperrung ", 17)
        conf["rpiDoor/relayPulseLength"] = ConsoleInputTools.get_number_input("Wie viele ms soll das Relais gehalten werden?", 250)
        conf["rpiDoor/openedPin"] = ConsoleInputTools.get_input("Pinnummer für Offen/Geschloßen", 27)
        conf["rpiDoor/closedPinHigh"] = ConsoleInputTools.get_bool_input("Tür zu = in high?")
        conf["rpiDoor/name"] = ConsoleInputTools.get_input("Sichtbarer Name")

    @staticmethod
    def runCalibrationProcess(conf: conf.BasicConfig, logger:logging.Logger):
        from Mods.DoorOpener.calibrate import Calibrate
        Calibrate.run_calibration(conf, logger)

class ExtendetEnums(enum.Enum):
    CLOSED   = "Geschlossen"
    OPEN     = "Geöffnet"
    UNLOCKED = "Entsperrt"

class OnOffEnum(enum.Enum):
    ON  = "ON"
    OFF = "OFF"

class DoorOpener:

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self.__client = client
        self.__logger = logger.getChild("PiDoorOpener")
        self._config = opts
        self._device_id = device_id
        self._registered_callback_topics = []
        self.input = None
        self.out = None
        self._config.get("rpiDoor/state/sw", default=OnOffEnum.OFF.value)
        self._config.get("rpiDoor/state/ex", default=ExtendetEnums.CLOSED.value)
        self._topic = None

    def register(self):
        try:
            self.__logger.debug("Regestriere Raspberry GPIO...")
            from gpiozero.pins.native import NativeFactory
            from gpiozero import Device

            Device.pin_factory = NativeFactory()
            self.__logger.debug("InputPin = %s", self._config["rpiDoor/openedPin"])
            self.input = gpiozero.Button(pin=self._config["rpiDoor/openedPin"])
            self.__logger.debug("OuputPin = %s", self._config["rpiDoor/unlockPin"])
            self.out   = gpiozero.LED(   pin=self._config["rpiDoor/unlockPin"])

            self.input.when_activated   = lambda: self.InputHandler(True )
            self.input.when_deactivated = lambda: self.InputHandler(False)

            schedule.every(15).minutes.do(self.sendUpdate)

            self.__logger.debug("Regestiere MQTT Topics")
            unique_id = "sensor.doorOpener-{}.{}".format(self._device_id, self._config["rpiDoor/name"].replace(" ", "_"))
            self.topic = self._config.get_autodiscovery_topic(conf.autodisc.Component.SWITCH, self._config["rpiDoor/name"], None)
            payload = self.topic.get_config_payload(self._config["rpiDoor/name"], None, unique_id=unique_id,
                            json_attributes=True, value_template="{{ value_json.sw }}")
            self.__client.publish(self.topic.config, payload=payload, qos=0, retain=True)
            self.__client.will_set(self.topic.ava_topic, "offline", retain=True)
            self.__client.publish(self.topic.ava_topic, "online", retain=True)

            self.__client.message_callback_add(self.topic.command, self.on_message)
            self._registered_callback_topics.append(self.topic.command)
            self.__client.subscribe(self.topic.command)
            self.sendUpdate()
        except Exception as e:
            self.__logger.exception("Register hat fehler verursacht!")
            raise e

    def sendUpdate(self, fromHandler=False):
        if not fromHandler:
            if self._config["rpiDoor/state/ex"] == ExtendetEnums.UNLOCKED.value:
                return
            self.InputHandler(self.input.value)
            return
        ex = self._config["rpiDoor/state/ex"]
        if ex == ExtendetEnums.UNLOCKED or ex == ExtendetEnums.OPEN.value:
            self._config["rpiDoor/state/sw"] = OnOffEnum.ON.value
        else:
            self._config["rpiDoor/state/sw"] = OnOffEnum.OFF.value
        self.__client.publish(self.topic.state, payload=json.dumps(self._config["rpiDoor/state"]))

    def InputHandler(self, high):
        # = true wenn tür zu = pin high ist
        self.__logger.debug("Input ist jetzt %d", int(high))
        self.__logger.debug("Geschloßen = high = %d", int(self._config["rpiDoor/closedPinHigh"]))
        if high == self._config["rpiDoor/closedPinHigh"]:
            #Tor ist zu
            self._config["rpiDoor/state/ex"] = ExtendetEnums.CLOSED.value
            self.__logger.debug("Tür ist zu")
        else:
            # Tor ist offen
            self._config["rpiDoor/state/ex"] = ExtendetEnums.OPEN.value
            self.__logger.debug("Tür ist offen")
        self.sendUpdate(True)

    def on_message(self, client, userdata, message: mclient.MQTTMessage):
        msg = message.payload.decode('utf-8')
        self.__logger.debug("on_message( {},{} )".format(message.topic, msg))
        if msg == OnOffEnum.ON.value:
            self.__logger.info("Tür wird entsperrt")
            self.out.blink(n=1)

    def stop(self):
        for reg in self._registered_callback_topics:
            self.__client.message_callback_remove(reg)