# -*- coding: utf-8 -*-

import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import Tools.Pin as Pin
import json
import schedule
import Tools.ResettableTimer as rtimer

import gpiozero

class PortaMatic:
    current_job = None
    _is_closed  = True
    last_trigger = "Nichts"
    _new_closed = True

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        self.current_job = rtimer.ResettableTimer(30, self.do_open, userval=None, autorun=False)

        from gpiozero.pins.native import NativeFactory
        from gpiozero import Device
        Device.pin_factory = NativeFactory()

        self.__client = client
        self.topic = None
        self.__logger = logger.getChild("PortaMatic")
        self._config = opts
        self._pins = {
            "isClosed": Pin.Pin(opts["PortaMatic/pins/isClosed"], Pin.PinDirection.IN),
            "inside"  : Pin.Pin(opts["PortaMatic/pins/inside"  ], Pin.PinDirection.IN),
            "outside" : Pin.Pin(opts["PortaMatic/pins/outside" ], Pin.PinDirection.IN),
            "tester"  : Pin.Pin(opts["PortaMatic/pins/tester"  ], Pin.PinDirection.IN),
            "pulseOut": Pin.Pin(opts["PortaMatic/pins/pulseOut"], Pin.PinDirection.IN)
        }
        self._device_id = device_id
        
        self._pins["isClosed"].set_detect(self.zu_handler,    Pin.PinEventEdge.BOTH)
        self._pins["inside"  ].set_detect(self.inside_handler, Pin.PinEventEdge.BOTH)
        self._pins["outside" ].set_detect(self.outside_handler, Pin.PinEventEdge.BOTH)
        self._pins["taster"  ].set_detect(self.taster_handler,  Pin.PinEventEdge.BOTH)

        self._schedJob = schedule.every().minute
        self._schedJob.do(self.check_inputs)


    def register(self):
        sensorName = self._config["PortaMatic/name"]
        uid_motion = "switch.PortaMatic-{}-{}".format(self._device_id, sensorName)
        self.topic = self._config.get_autodiscovery_topic(
            conf.autodisc.Component.SWITCH,
            sensorName,
            conf.autodisc.Component.SWITCH
        )
        payload = self.topic.get_config_payload(
            sensorName, "", unique_id=uid_motion, value_template="{{ value_json.is_open }}", json_attributes=True)
        if self.topic.config is not None:
            self.__client.publish(self.topic.config,
                                  payload=payload, qos=0, retain=True)
        self.__client.publish(
            self.topic.ava_topic, "online", retain=True)
        self.__client.will_set(
            self.topic.ava_topic, "offline", retain=True)
        self.__client.subscribe(self.topic.command)
        self.__client.message_callback_add(self.topic.command, self.on_message)
        self.check_inputs()
        self.sendStates()

    def check_inputs(self):
        self._is_closed = self._pins["isClosed"].input()
        self.sendStates()

    def zu_handler(self, device):
        if not self._pins["zu"].input():
            self.__logger.info("Tor ist zu")
            self._is_closed = True
        else:
            self.__logger.info("Tor ist nicht mehr zu")
            self._is_closed = False
        self.sendStates()

    def inside_handler(self, device: gpiozero.Button):
        self.main_handler(device.value, True, False, False, False)

    def outside_handler(self, device: gpiozero.Button):
        self.main_handler(device.value, False, False, False, False)

    def taster_handler(self, device: gpiozero.Button):
        self.main_handler(device.value, False, False, True, False)

    def main_handler(self, signal: bool, inside: bool, stay: bool, manuell: bool, mqtt: bool):
        # Einweg Modus prüfen (aka Außensensor deaktiviert)
        if not inside and not manuell and not mqtt and self._config.get("PortaMatic/v/one_way", False):
            self.__logger.warning("Einweg")
            return
        # Offenbleiben überschreibung prüfen
        if not signal and not manuell and not mqtt and self._config.get("PortaMatic/v/stay", False):
            self.__logger.warning("Offen Bleiben")
            return
        if mqtt:
            self.last_trigger = "MQTT"
        elif manuell:
            self.last_trigger = "Manuell"
        elif inside:
            self.last_trigger = "Innen Bewegung"
        else:
            self.last_trigger = "Außen Bewegung"
        if not signal:
            self._config["PortaMatic/v/stay"] = False
        elif mqtt:
            self._config["PortaMatic/v/stay"] = True
        self.open_close(not signal)

    def res_handler(self, device):
        pass

    def sendStates(self):
        payload_js = {
            "offen"  : not self._is_closed,
            "Einbahn": self._config.get("PortaMatic/v/one_way", False),
            "Bleib"  : self._config.get("PortaMatic/v/stay", False),
            "Auslöser": self.last_trigger,
            "Schließzeit": self._config.get("PortaMatic/v/secs_to_close", 5)
        }
        payload = json.dumps(payload_js)
        self.__client.publish(self.topic.state, payload=payload)
        self.do_open()

    def stop(self):
        schedule.cancel_job(self._schedJob)
        if self.current_job is not None:
            schedule.cancel_job(self.current_job)
    
    def open_close(self, open=False):
        self._new_closed = open
        self.do_open()

    def do_open(self):
        self.current_job.cancel()
        if self._is_closed is not self._new_closed:
            self._pins["pulseOut"].pulse()
            self.current_job.start()
            
    def on_message(self, client, userdata, message: mclient.MQTTMessage):
        payload = message.payload.decode('utf-8')
        self.__logger.debug("on_message( {},{} )".format(message.topic, payload))
        if payload == "OPEN":
            self.open_close(True)
        elif payload == "CLOSE":
            self.open_close(False)

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "PortaMatic"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return PortaMatic(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        raise NotImplementedError()

