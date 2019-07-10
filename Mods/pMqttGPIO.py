# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
from Tools import Config, Pin, Autodiscovery, ConsoleInputTools
import logging
import time
import schedule

try:
    import gpiozero
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('gpiozero', throw=ie, ask=True)
    except err.RestartError:
        import gpiozero

class PluginLoader:
    @staticmethod
    def getConfigKey():
        return "RaspberryPiGPIO"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: Config.BasicConfig, logger: logging.Logger, device_id: str):
        return RaspberryPiGpio(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: Config.BasicConfig, logger:logging.Logger):
        conf["RaspberryPiGPIO"] = []
        while True:
            from builtins import KeyboardInterrupt
            try:
                dir_str = "Bitte eine der Nummern eingeben um die Richtung des Pins einzustellen. \nOUT = 0, IN = 1, IN_PULL_UP = 2, IN_PULL_LOW = 3 "
                from builtins import input
                d = {
                    "Pin": ConsoleInputTools.get_number_input("Pin Nummer eingeben: "),
                    "name": input("Sichtbarer Name des Pins: ")
                }
                direction = Pin.PinDirection(ConsoleInputTools.get_number_input(dir_str))
                d["direction"] = direction.value
                if direction == Pin.PinDirection.OUT:
                    isPulse = ConsoleInputTools.get_bool_input("Soll der Pin nur gepullst werden?", False)
                    d["isPulse"] = isPulse
                pulse_width = ConsoleInputTools.get_number_input("Bitte ms eingeben, die beim PULSE gehalten werden sollen [250ms]: ", -1)
                if pulse_width != -1:
                    d["pulse_width"] = pulse_width
                conf.get("RaspberryPiGPIO", []).append(d)
                print("\nHinzugefügt.\nWenn nichts mehr hinzugefügt werden soll CTRL-C drücken\n")
            except KeyboardInterrupt:
                i = input("Pin hinzufügen abgebrochen. Wiederholen? [y/N]")
                if i != "y" and i != "Y":
                    break


class RaspberryPiGpio:

    def __init__(self, client: mclient.Client, opts: Config.BasicConfig, logger: logging.Logger, device_id: str):
        self.__client = client
        self.__logger = logger.getChild("rPiGPIO")
        self._config = opts
        self._pins = []
        self._device_id = device_id
        self._registered_callback_topics = []

    def register(self):
        self.__logger.debug("Regestriere Raspberry GPIO...")
        from gpiozero.pins.native import NativeFactory
        from gpiozero import Device

        Device.pin_factory = NativeFactory()

        for p in self._config.get("RaspberryPiGPIO", []):
            pin = Pin.Pin(p["Pin"], Pin.PinDirection(p["direction"]))
            if p.get("pulse_width", None) is not None:
                pin.set_pulse_width(p["pulse_width"])
            d = {
                "n": p["name"],
                "p": pin
            }
            if pin.get_direction() == Pin.PinDirection.OUT:
                t = self._config.get_autodiscovery_topic(Autodiscovery.Component.SWITCH, p["name"], Autodiscovery.SensorDeviceClasses.GENERIC_SENSOR)
            else:
                t = self._config.get_autodiscovery_topic(Autodiscovery.Component.BINARY_SENROR, p["name"], Autodiscovery.BinarySensorDeviceClasses.GENERIC_SENSOR)
            d["t"] = t
            if p.get("meassurement_value", None) is not None:
                d["mv"] = p["meassurement_value"]
            else:
                d["mv"] = ""
            if p.get("isPulse", None) is not None:
                d["isPulse"] = p["isPulse"]
            else:
                d["isPulse"] = False
            if d.get("init", None) is not None:
                pin.output(d["init"])
            self._pins.append(d)
            self.__logger.debug("Pin config gebaut. N: {}, P: {}, D: {}, isPulse: {}".format(d["n"], p["Pin"], pin.get_direction(), d["isPulse"]))
        for d in self._pins:
            self.register_pin(d)
        self.__logger.debug("Regestriere Schedule Jobs für ¼ Stündliche resend Aufgaben...")
        schedule.every(15).minutes.do(RaspberryPiGpio.send_updates, self)

    def register_pin(self, d: dict):
        pin = d["p"]
        name = d["n"]
        topic = d["t"]
        meas_val = d["mv"]
        online_topic = "device_online/piGPIO/{}/onlinePins".format(self._device_id)
        self.__logger.debug("Regestriere {} unter {}".format(name, topic.state))

        if pin.get_direction() == Pin.PinDirection.OUT:
            uid = "switch.rPiGPIO-{}.{}".format(Autodiscovery.Topics.get_std_devInf().pi_serial, name.replace(" ", "_"))
            self.__logger.debug("Pushe Config")
            if topic.config is not None:
                self.__client.publish(topic.config, topic.get_config_payload(name, meas_val, online_topic, unique_id=uid), retain=True)
            self.__logger.debug("LWT push")
            self.__client.will_set(online_topic, "offline", retain=True)
            self.__client.publish(online_topic, "online", retain=True)
            self.__logger.debug("SUB")
            self.__client.subscribe(topic.command)
            time.sleep(2)
            self.__logger.debug("Bin switch. Regestriere msqtt callback unter {}".format(topic.command))
            self.__client.message_callback_add(topic.command, self.on_message)
            self._registered_callback_topics.append(topic.command)

        else:
            self.__logger.debug("Bin kein switch. Brauche kein callback.")
            uid = "binary_sensor.rPiGPIO-{}.{}".format(Autodiscovery.Topics.get_std_devInf().pi_serial,  name.replace(" ", "_"))
            if topic.config is not None:
                self.__client.publish(topic.config, topic.get_config_payload(name, meas_val, online_topic, unique_id=uid), retain=True)
            self.__client.will_set(online_topic, "offline", retain=True)
            self.__client.publish(online_topic, "online", retain=True)
            pin.set_detect(self.send_updates, Pin.PinEventEdge.BOTH)
        self.send_updates()

    def on_message(self, client, userdata, message: mclient.MQTTMessage):
        self.__logger.debug("on_message( {},{} )".format(message.topic, message.payload.decode('utf-8')))
        for d in self._pins:
            if d["t"].command == message.topic:
                if message.payload.decode('utf-8') == "ON" and d["isPulse"]:
                    d["p"].pulse()
                elif message.payload.decode('utf-8') == "ON":
                    self.__logger.debug("Einschalten")
                    d["p"].turnOn()
                elif message.payload.decode('utf-8') == "OFF":
                    self.__logger.debug("Ausschalten")
                    d["p"].turnOff()
                elif message.payload.decode('utf-8') == "PULSE":
                    d["p"].pulse()
                self.send_updates()
                return
        self.__logger.warning("Habe keinen Pin für message gefunden :(")

    def sendStates(self):
        self.send_updates()

    def stop(self):
        for reg in self._registered_callback_topics:
            self.__client.message_callback_remove(reg)

    @staticmethod
    def convert_input_to_string(to_convert: int) -> str:
        if to_convert == 0:
            return "OFF"
        elif to_convert == 1:
            return "ON"

    def send_updates(self):
        for d in self._pins:
            pin = d["p"]
            topic = d["t"]
            self.__client.publish(topic.state, self.convert_input_to_string(pin.input()))