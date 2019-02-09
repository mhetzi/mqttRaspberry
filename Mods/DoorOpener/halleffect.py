# -*- coding: utf-8 -*-
import threading
import Adafruit_ADS1x15
import RPi.GPIO as GPIO
import Tools.Pin as p
import Tools.Config
import enum
import logging
import time
import math

ALERT_PIN = 33
GAIN = 1
CHANNEL_ZU = 0
CHANNEL_MIDDLE = 1
CHANNEL_MIDDLE2 = 2
CHANNEL_OFFEN = 3

class DoorStateEnum(enum.Enum):
    FEHLER = 1
    BEWEGUNG = 2
    EXTERN = 3
    SUCHE_POS = 4
    STOPPED = 5
    CALIBRATE = 6
    OK = 7
    NO_POS_COMMAND_IGNORED = 8

class Halleffekt:
    __last_pos = 0
    __last_channel = 0
    __to_pos = -1
    __is_moving = False

    def __init__(self, opts: Tools.Config.BasicConfig, logger: logging.Logger):
        self.on_state = self._on_state
        self.on_changing = self._on_changing
        self.on_pulse = self._on_pulse
        self._config = opts
        self._logger = logger.getChild("Halleffekt")
        GPIO.setup(opts.get("rpiDoor/Hall/ALERT_PIN", ALERT_PIN), GPIO.IN)
        GPIO.add_event_detect(opts.get("rpiDoor/Hall/ALERT_PIN", ALERT_PIN), GPIO.RISING, callback=self._process_adc_event, bouncetime=10)
        self.__adc = Adafruit_ADS1x15.ADS1115(address=opts.get("rpiDoor/Hall/ADC_ADDR", 0x49))
        self.__do_track_motion = threading.Event()
        self.__do_track_motion.set()
        self.__do_shutdown = False
        self.__doorStateComperator = DoorStateEnum.FEHLER
        self.error = False

    def _on_state(self, ds: DoorStateEnum):
        self._logger.warning("Tür status wird nicht verarbeitet. " + str(ds))

    def _on_changing(self, percent: int):
        self._logger.warning("Tür Prozentwert wird nicht verarbeitet. " + str(percent))

    def _on_pulse(self):
        self._logger.warning("Tür kann nicht verändert werden. on_pulse ist nicht implementiert.")

    def _startup_check_pos(self, wait_time=None, trys= 0, last_checked_pos=None, retrys=0):
        if wait_time is None:
            wait_time = self._config.get("rpiDoor/Hall/pos_missed_read_wait", 7.0)
        self.__last_pos = -1
        self.__last_channel = -1
        do_check = True
        self.on_state(DoorStateEnum.SUCHE_POS)
        channel_positions = self._config.get("rpiDoor/Hall/Channels_Position", [0, 50, 100, -1])
        gain = self._config.get("rpiDoor/Hall/GAIN", 1)
        while True:
            for i in range(0, 4):
                if channel_positions[i] > -1:
                    val = self.__adc.read_adc(channel=i, gain=gain, data_rate=8)
                    if self._config["rpiDoor/Hall/Kalib/minMaxPoints"][i] < val < self._config["rpiDoor/Hall/Kalib/posMaxPoints"][i]:
                        self.__last_channel = i
                        self.__last_pos = channel_positions[i]
                        do_check = False
            if do_check:
                time.sleep(wait_time)
            else: break
            self.on_state(DoorStateEnum.SUCHE_POS)

        self._logger.info("Gefundene Position {} auf Kanal {}".format(self.__last_pos, self.__last_channel))
        self.set_move_detect()
        self.on_state(DoorStateEnum.OK)

    # Positionen können sein -2 STOP oder 0 - 100
    def __move_to_position(self, pos: int, _retry=0):
        if self.__do_shutdown:
            return False
        if pos == -2 and self.__is_moving:
            self.on_pulse()
            self.on_state(DoorStateEnum.STOPPED)
            return True
        elif pos != self.__last_pos and self.__last_pos != -1:
            self.__to_pos = pos
            self.on_pulse()
            self.set_move_detect()
            self._logger.debug("Tor bewegt sich zu Position. Warte {}".format(self._config.get("rpiDoor/Hall/max_move_time", 12)))
            self.on_state(DoorStateEnum.BEWEGUNG)
            if not self.__do_track_motion.wait(  self._config.get("rpiDoor/Hall/max_move_time", 12) ):
                if _retry > self._config.get("rpiDoor/Hall/max_move_retrys", 3):
                    self._logger.warning("Tor FEHLER, nach {} immer nicht in Position.".format( self._config.get("rpiDoor/Hall/max_move_retrys", 3) ))
                    self.__to_pos = -1
                    self.error = True
                    self.on_state(DoorStateEnum.FEHLER)
                    return False
                self._logger.warning("Tor nicht in Position")
                self.__move_to_position(pos=pos, _retry=_retry + 1)
                return False
            else:
                self.__to_pos = -1
                self._logger.info("Tor müsste in gewünschter Position sein.")
                self.on_state(DoorStateEnum.OK)
                return True
        elif pos == self.__last_pos:
            self._logger.debug("Tor ist schon in position.")
            return True
        elif self.__last_pos == -1:
            self._logger.warning("Tor hat keine Position. Werden nichts tun, um schäden zu vermeiden.")
            self.on_state(DoorStateEnum.NO_POS_COMMAND_IGNORED)
            raise Exception("Jump over check_pos() Exception, einfach ignorieren")

    def move_to_position(self, pos) -> bool:
        """
        Bewege zu Position
        :param pos: Position
        :return: Bewegen erfolgreich
        """
        val = self.__move_to_position(pos=pos)
        self._startup_check_pos()
        return val

    def set_move_detect(self):
        channel_positions = self._config.get("rpiDoor/Hall/Channels_Position", [0, 50, 100, -1])
        zp = self._config.get("rpiDoor/Hall/Kalib/zeroPoints", [-1, -1, -1, -1])
        mp = self._config.get("rpiDoor/Hall/Kalib/posMaxPoints", [-1, -1, -1, -1])
        np = self._config.get("rpiDoor/Hall/Kalib/minMaxPoints", [-1, -1, -1, -1])
        if self.__to_pos > -1:
            # Muss Position erreichen, wenn erreicht wecke Raspberry
            for i in range(0, len(channel_positions)):
                if channel_positions[i] == self.__to_pos:
                    self.__adc.start_adc_comparator(channel=i, gain=self._config.get("rpiDoor/Hall/GAIN", 1),
                                                    active_low=False, traditional=True, latching=False,
                                                    num_readings=self._config.get("rpiDoor/Hall/adc_readings", 2),
                                                    high_threshold=math.ceil(zp[i] + mp[i]),
                                                    low_threshold=math.floor(zp[i] + np[i]), data_rate=8
                                                    )
                    break
        elif self.__last_pos > -1:
            # Habe Position, wenn verlassen wird wecke Raspberry
            for i in range(0, len(channel_positions)):
                if channel_positions[i] == self.__last_pos:
                    self.__adc.start_adc_comparator(channel=i, gain=self._config.get("rpiDoor/Hall/GAIN", 1),
                                                    active_low=False, traditional=False, latching=False,
                                                    num_readings=self._config.get("rpiDoor/Hall/adc_readings", 2),
                                                    high_threshold=math.ceil(zp[i] + mp[i]),
                                                    low_threshold=math.floor(zp[i] + np[i]), data_rate=8
                                                    )
                    self.on_changing(self.__last_pos)
                    break

    def _process_adc_event(self, channel):
        if self.__to_pos > -1:
            self.__do_track_motion.set()
        else:
            self.on_state(DoorStateEnum.EXTERN)
            self._startup_check_pos()
