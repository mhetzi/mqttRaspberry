# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import logging
import threading
import RPi.GPIO as GPIO
import Tools.Pin as p
import Tools.Config as tc
import Tools.ThreadedMqttMessageHandler as thrMsg
import Mods.DoorOpener.halleffect as hall
import enum
import time


class DoorDetectType(enum.Enum):
    HALL_EFFECT = 0
    IR_DISTANCE = 2


class DoorOpener:
    # - active_low: Boolean that indicates if ALERT is pulled low or high
    #               when active/triggered.  Default is true, active low.
    # - traditional: Boolean that indicates if the comparator is in traditional
    #                mode where it fires when the value is within the threshold,
    #                or in window mode where it fires when the value is _outside_
    #                the threshold range.  Default is true, traditional mode.
    # - latching: Boolean that indicates if the alert should be held until
    #             get_last_result() is called to read the value and clear
    #             the alert.  Default is false, non-latching.
    # - num_readings: The number of readings that match the comparator before
    #                 triggering the alert.  Can be 1, 2, or 4.  Default is 1.
    def __init__(self, client: mclient.Client, opts: tc.BasicConfig, logger: logging.Logger, device_id: str):
        GPIO.setmode(GPIO.BOARD)
        self.__mqtt = client
        self._config = opts
        self.logger = logger.getChild("DoorOpener."+str(opts.get("rpiDoor/Hall/ADC_ADDR", 0x49)))
        self.__door_name = opts.get("rpiDoor/name", "Kein Name")
        self.relayPin = None
        self.halleffekt = None
        self._thr = None

    def register(self):
        def thr_reg():
            self.logger.debug("Baue Halleffekt auf 2ten Thread")
            self.relayPin = p.Pin(pin=self._config.get("rpiDoor/relayPin", 0), direction=p.PinDirection.OUT, init=0)
            self.halleffekt = hall.Halleffekt(self._config, logger=self.logger)

            self.halleffekt.on_changing = self.open_pos_update
            self.halleffekt.on_state = self.status_update
            self.halleffekt.on_pulse = lambda: self.relayPin.pulse(self._config.get("rpiDoor/relayPulseLength", 250))

            self._thr = thrMsg.MqttMessageThread(self.__mqtt, "secure/door/{}/set".format(self.__door_name), self.do_your_thing, self.logger)
            self._thr.set_cancel_new_while_running(val=True)
            self.halleffekt._startup_check_pos(30)

        t = threading.Timer(0.1, thr_reg)
        t.start()

    def stop(self):
        if self._thr is not None:
            self._thr.kill()

    def send_update(self):
        pass

    def status_update(self, ds: hall.DoorStateEnum):
        update_text = ""

        if ds == hall.DoorStateEnum.BEWEGUNG:
            update_text = "Bewege zu Position"
        elif ds == hall.DoorStateEnum.STOPPED:
            update_text = "Angehalten"
        elif ds == hall.DoorStateEnum.SUCHE_POS:
            update_text = "Position wird gesucht..."
        elif ds == hall.DoorStateEnum.EXTERN:
            update_text = "Position wurde von außerhalb verändert"
        elif ds == hall.DoorStateEnum.FEHLER:
            update_text = "Ein Fehler ist aufgetreten"
        elif ds == hall.DoorStateEnum.CALIBRATE:
            update_text = "Sensor wird Kalibriert"
        elif ds == hall.DoorStateEnum.OK:
            update_text = "OK"
        elif ds == hall.DoorStateEnum.NO_POS_COMMAND_IGNORED:
            update_text = "Kommando ignoriert! Tor hat (noch) keine Position."

        self.__mqtt.publish("secure/door/{}/extendet_state".format(self.__door_name), update_text, qos=0, retain=True)

    def open_pos_update(self, percent: int):
        self.__mqtt.publish("secure/door/{}/state".format(self.__door_name), str(percent), qos=0, retain=True)

    def do_your_thing(self, client, userdata, message: mclient.MQTTMessage):
        decoded = message.payload.decode()
        try:
            go_to_position = int(decoded)
        except ValueError:
            if decoded == "CLOSE":
                go_to_position = 0
            elif decoded == "OPEN":
                go_to_position = 100
            elif decoded == "STOP":
                go_to_position = -2
            elif decoded == "DEBUG_PULSE_RELAY_PIN":
                self.logger.info("Debug Funktion PULSE_RELAY_PIN aufgerufen")
                self.relayPin.pulse(self._config.get("rpiDoor/relayPulseLength", 250))
                return
            elif decoded == "DEBUG_RECHECK_POSITION":
                self.logger.info("Debug Funktion RECHECK POSITION aufgerufen")
                self.halleffekt._startup_check_pos(trys=1)
                return
            elif decoded == "DEBUG_TOGGLE_RELAY_PIN":
                self.logger.warning("Debug Funktion Relais umschalten.\nDies kann zu probleme verursachen wenn der Antrieb angeschlossen ist!")
                self.relayPin.toggle()
                return
            elif decoded.startswith("run://"):
                arr = decoded.replace("run://", "").split("&&")
                for a in arr:
                    if "POS" in a:
                        a = a.replace("POS", "")
                        self.logger.debug("Gehe zu Position: {}".format(a))
                        if not self.halleffekt.move_to_position(int(a)):
                            self.logger.warning("Skript wird abgebrochen! Zu Position bewegen war nicht erfolgreich!")
                            break
                    elif "SLEEP" in a:
                        a = int(a.replace("SLEEP", ""))
                        self.logger.debug("Schlafe jetzt {} Sekunden".format(a))
                        time.sleep(a)
                return
            else:
                self.logger.error("Kommando {} nicht verstanden!".format(decoded))
                return
        self.halleffekt.move_to_position(go_to_position)
