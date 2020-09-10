# -*- coding: utf-8 -*-

import paho.mqtt.client as mclient
import Tools.Config as conf
import logging
import json
import time
import datetime
import schedule

# Platine Belegung
# Taster Pin_22 GPIO_25
#
# Reed_1 Pin_16 GPIO_23
# Reed_2 Pin_18 GPIO_24
# Reed_3 Pin_15 GPIO_22

import Tools.Pin as Pin

class Plugin:
    _is_open   = False
    _is_ho     = False
    _is_half   = False
    _is_hc     = False
    _is_closed = False
    _is_open_overshoot = False
    STOP       = False
    target_pos = 0
    current_pos = 0
    is_moving = False
    do_move   = False
    moves_since = None
    current_job = None
    open_time = None
    open_overshoot_delta = datetime.timedelta(seconds=2)

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        from gpiozero.pins.native import NativeFactory
        from gpiozero import Device
        Device.pin_factory = NativeFactory()

        self.__client = client
        self.topic = None
        self.__logger = logger.getChild("pi_garage")
        self._config = opts
        self._pins = {
            "zu"   : Pin.Pin(opts["PiGarageSwitches/pins/zu"]      , Pin.PinDirection.IN),
            "mitte": Pin.Pin(opts["PiGarageSwitches/pins/mitte"]   , Pin.PinDirection.IN),
            "offen": Pin.Pin(opts["PiGarageSwitches/pins/offen"]   , Pin.PinDirection.IN),
            "stop" : Pin.Pin(opts["PiGarageSwitches/pins/stop"]    , Pin.PinDirection.IN),
            "relais": Pin.Pin(opts["PiGarageSwitches/relayPin"]    , Pin.PinDirection.OUT),
            "res": Pin.Pin(opts["PiGarageSwitches/pins/sperren"]   , Pin.PinDirection.IN)
        }
        self._device_id = device_id
        
        self._pins["zu"].set_detect(self.zu_handler, Pin.PinEventEdge.BOTH)
        self._pins["mitte"].set_detect(self.mitte_handler, Pin.PinEventEdge.BOTH)
        self._pins["offen"].set_detect(self.offen_handler, Pin.PinEventEdge.BOTH)
        self._pins["stop"].set_detect(self.stop_handler, Pin.PinEventEdge.BOTH)

        self._schedJob = schedule.every().minute
        self._schedJob.do(self.check_inputs)

    def register(self):
        sensorName = self._config["PiGarageSwitches/name"]
        uid_motion = "cover.pigaragesw-{}-{}".format(self._device_id, sensorName)
        self.topic = self._config.get_autodiscovery_topic(
            conf.autodisc.Component.COVER,
            sensorName,
            conf.autodisc.CoverDeviceClasses.GARAGE
        )
        payload = self.topic.get_config_payload(
            sensorName, "", unique_id=uid_motion, value_template="{{ value_json.position }}", json_attributes=True)
        if self.topic.config is not None:
            self.__client.publish(self.topic.config,
                                  payload=payload, qos=0, retain=True)
        self.__client.subscribe(self.topic.command)
        self.__client.message_callback_add(self.topic.command, self.on_message)

        self.check_inputs()

        self.sendStates()

    def check_inputs(self):
        if not self._pins["zu"].input():
            self.zu_handler(None)
        elif not self._pins["mitte"].input():
            self.mitte_handler(None)
        elif not self._pins["offen"].input():
            self.offen_handler(None)
        elif not self._pins["stop"].input():
            self.stop_handler(None)

    def zu_handler(self, device):
        if not self._pins["zu"].input():
            self.__logger.info("Tor ist zu")
            self._is_closed = True
            self._is_hc = False
            self._is_ho = False
        else:
            self.__logger.info("Tor ist nicht mehr zu")
            self._is_hc = True
            self._is_closed = False
        self.sendStates()
    
    def mitte_handler(self, device):
        if not self._pins["mitte"].input():
            self.__logger.info("Tor ist mittig")
            self._is_half = True
        elif self._is_hc:
            self.__logger.info("Tor ist auf dem weg zu auf")
            self._is_hc = False
            self._is_ho = True
            self._is_half = False
        elif self._is_ho:
            self.__logger.info("Tor ist auf dem weg zu zu")
            self._is_hc = True
            self._is_ho = False
            self._is_half = False
        else:
            self.__logger.info("Tor ist nicht mehr mittig")
            self._is_hc = True
            self._is_ho = True
            self._is_half = False
        self.sendStates()

    def offen_handler(self, device):
        if not self._pins["offen"].input():
            self.__logger.info("Tor ist offen")
            self._is_open = True
            self._is_hc = False
            self._is_ho = False
            self.open_time = datetime.datetime.now()
        else:
            if self.open_time is not None and self.open_time > (datetime.datetime.now() - self.open_overshoot_delta) and not self._is_open_overshoot:
                self.__logger.info("Tor ist immer noch offen, overshoot entdeckt.")
                self._is_open_overshoot = True
                self._is_ho = False
                self._is_open = True
            else:
                self.__logger.info("Tor ist nicht mehr offen")
                self._is_open_overshoot = False
                self._is_ho = True
                self._is_open = False
        self.sendStates()

    def stop_handler(self, device, force=False):
        self.STOP = not self._pins["stop"].input() or force
        if self.STOP:
            if self._is_hc or self._is_ho:
                self.pulseRelay()
        self.sendStates()
        self.__client.message_callback_remove(self.topic.command)
        self.__client.unsubscribe(self.topic.command)

    def res_handler(self, device):
        pass

    def sendStates(self):
        pos  = 0
        if self._is_closed:
            pos = 0
        elif self._is_half:
            pos = 50
        elif self._is_open or self._is_open_overshoot:
            pos = 100
        elif self._is_hc and self._is_ho:
            pos = 50
        elif self._is_hc:
            pos = 25
        elif self._is_ho:
            pos = 75
        self.current_pos = pos
        payload_js = {
            "position": pos,
            "offen": self._is_open,
            "offen übersprungen": self._is_open_overshoot,
            "mitte": self._is_half,
            "zu":    self._is_closed,
            "zuMitte": self._is_hc,
            "offenMitte": self._is_ho,
            "STOP": self.STOP
        }
        payload = json.dumps(payload_js)
        self.__client.publish(self.topic.state, payload=payload)
        self.move_to()

    def stop(self):
        schedule.cancel_job(self._schedJob)
        if self.current_job is not None:
            schedule.cancel_job(self.current_job)

    def pulseRelay(self):
        self._pins["relais"].pulse(self._config.get("PiGarageSwitches/relayPulseLength", 250))
    
    def move_to(self, pos=None, attempt=0, checker=None):
        self.__logger.debug("move_to(pos={}, attempt={}, checker={})".format(pos if pos is not None else "None", attempt, checker is not None))
        if pos is not None and self.current_pos != pos:
            self.__logger.info("Neue Position, sollte mich bewegen")
            self.target_pos = pos
            self.do_move = True
        if checker is not None:
            self.__logger.info("Checker ist da, brich den JOB ab")
            schedule.cancel_job(checker)
            self.current_job = None
            if attempt >= self._config["PiGarageSwitches/Hall/max_move_retrys"]:
                self.do_move = False
                self.is_moving = False
                return
            if self.target_pos != self.current_pos:
                self.__logger.debug("Checker ({}) ist nicht auf Position ({}) setze do_move".format(self.target_pos, self.current_pos))
                if self.target_pos == 50 and (self.current_pos == 25 or self.current_pos == 75):
                    self.__logger.debug("Bin doch auf position... ")
                    self.do_move = False
                    self.is_moving = False
                else:
                    self.do_move = True
                    self.is_moving = False
        if self.do_move and not self.is_moving and not self.STOP and self.current_job is None:
            self.is_moving = True
            self.__logger.info("Bewege mich nicht, soll aber. Schalte...")
            self.pulseRelay()
            if self.current_job is None:
                job = schedule.every(self._config["PiGarageSwitches/Hall/max_move_time"]).seconds
                job.do(self.move_to, attempt=attempt+1, checker=job)
                self.current_job = job
        if self.target_pos == self.current_pos and self.current_pos != 0 and self.current_pos != 100:
            self.__logger.info("Bin auf position. Schalte um zum stehen zu kommen.")
            self.pulseRelay()
        if self.target_pos == self.current_pos:
            self.is_moving = False
            self.do_move = False
            self.__logger.info("Bin auf fester Position.")
            if self.current_job is not None:
                self.__logger.debug("Cancel Checker -> pos stimmt")
                schedule.cancel_job(self.current_job)
                self.current_job = None
        

    def on_message(self, client, userdata, message: mclient.MQTTMessage):
        payload = message.payload.decode('utf-8')
        self.__logger.debug("on_message( {},{} )".format(message.topic, payload))
        if payload == "OPEN":
            self.move_to(100)
        elif payload == "CLOSE":
            self.move_to(0)
        elif payload == "STOP":
            self.stop_handler(None, True)
        else:
            i = int(payload)
            if i > 0 and i < 55:
                i = 50
            elif i > 54:
                i = 100
            self.move_to(i)
                

class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "PiGarageSwitches"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return Plugin(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools

        rpin = ConsoleInputTools.get_number_input("Pin Nummer des Taster Relais ", 22)
        delay = ConsoleInputTools.get_number_input("Wie viele ms soll das Relais gehalten werden?", 250)

        
        input_zu = ConsoleInputTools.get_number_input("Pin für Position ZU?")
        input_mitte = ConsoleInputTools.get_number_input("Pin für Position MITTE?", -1)
        input_offen = ConsoleInputTools.get_number_input("Pin für Position OFFEN?")
        input_stop = ConsoleInputTools.get_number_input("STOP Pin?", -1)
        input_lock = ConsoleInputTools.get_number_input("LOCK Pin?", -1)

        door_open_time = ConsoleInputTools.get_number_input("Wie lange braucht das Tor von zu bis auf oder umgekehrt maximal?\n>", 15)
        door_open_retry = ConsoleInputTools.get_number_input("Wie oft soll versucht werden das Tor in die Position zu bringen?\n>", 3)
        name = ConsoleInputTools.get_input("Wie heißt das Tor?", require_val=True)

        conf["PiGarageSwitches/relayPin"] = rpin
        conf["PiGarageSwitches/relayPulseLength"] = delay
        conf["PiGarageSwitches/Hall/max_move_time"] = door_open_time
        conf["PiGarageSwitches/Hall/max_move_retrys"] = door_open_retry
        conf["PiGarageSwitches/name"] = name

        conf["PiGarageSwitches/pins/zu"]      = input_zu
        conf["PiGarageSwitches/pins/mitte"]   = input_mitte
        conf["PiGarageSwitches/pins/offen"]   = input_offen
        conf["PiGarageSwitches/pins/stop"]    = input_stop
        conf["PiGarageSwitches/pins/sperren"] = input_lock
