# -*- coding: utf-8 -*-
import RPi.GPIO as GPIO
import enum
import time

class PinDirection(enum.Enum):
    OUT = 0
    IN = 1
    IN_PULL_UP = 2
    IN_PULL_LOW = 3

class PinEventEdge(enum.Enum):
    RISING = 0
    FALLING = 1
    BOTH = 3

class Pin:

    def __init__(self, pin: int, direction: PinDirection, init=-1):
        self._pin = pin
        self._pulse_width = None
        self._direction = direction
        self._out = False

        if direction == PinDirection.IN:
            GPIO.setup(pin, GPIO.IN)
        elif direction == PinDirection.OUT:
            GPIO.setup(pin, GPIO.OUT)
        elif direction == PinDirection.IN_PULL_LOW:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        elif direction == PinDirection.IN_PULL_UP:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        else:
            raise Exception("Pin richtung ist falsch")

        if init != -1:
            self.output(bool(init))
        elif direction == PinDirection.OUT:
            self.output(False)

    def turnOn(self):
        self.output(True)

    def turnOff(self):
        self.output(False)

    def toggle(self):
        print("Pin ist jetzt {} und wird {}".format(self.input(), not self.input()))
        self.output(not self.input())

    def set_pulse_width(self, delay):
        self._pulse_width = delay

    def pulse(self, delay_ms=250):
        self.toggle()
        if self._pulse_width is not None:
            time.sleep(self._pulse_width / 1000)
        else:
            time.sleep(delay_ms/1000)
        self.toggle()

    def input(self) -> bool:
        if self._direction == PinDirection.OUT:
            return self._out
        return GPIO.input(self._pin)

    def output(self, val: bool):
        self._out = val
        try:
            GPIO.output(self._pin, val)
        except RuntimeError as x:
            if self._direction == PinDirection.OUT:
                print("Switch to output")
                GPIO.setup(self._pin, GPIO.OUT)
                GPIO.output(self._pin, val)

    def get_direction(self):
        return self._direction

    def set_detect(self, callback, level: PinEventEdge):
        if level == PinEventEdge.RISING:
            GPIO.add_event_callback(self._pin, GPIO.RISING, callback)
        elif level == PinEventEdge.FALLING:
            GPIO.add_event_callback(self._pin, GPIO.FALLING, callback)
        elif level == PinEventEdge.BOTH:
            GPIO.add_event_callback(self._pin, GPIO.BOTH, callback)
