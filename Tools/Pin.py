# -*- coding: utf-8 -*-
try:
    from gpiozero import LED, Button
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('gpiozero', throw=ie, ask=True)
    except err.RestartError:
        from gpiozero import LED, Button
import enum
import time
import logging

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
        self._underlying = None

        if init == -1:
            init = None

        if direction == PinDirection.IN:
            self._underlying = Button(pin=pin, pull_up=None, active_state=True)
        elif direction == PinDirection.OUT:
            self._underlying = LED(pin=pin, active_high=True, initial_value=init)
        elif direction == PinDirection.IN_PULL_LOW:
            self._underlying = Button(pin=pin, pull_up=False)
        elif direction == PinDirection.IN_PULL_UP:
            self._underlying = Button(pin=pin, pull_up=True)
        else:
            raise Exception("Pin richtung ist falsch")

    def turnOn(self):
        self._underlying.on()
        logging.getLogger("Launch").getChild("Tools.Pin").debug("turnON({})".format(self._pin))

    def turnOff(self):
        logging.getLogger("Launch").getChild("Tools.Pin").debug("turnOff({})".format(self._pin))
        self._underlying.off()

    def toggle(self):
        logging.getLogger("Launch").getChild("Tools.Pin").debug("Pin {} ist jetzt {} und wird {}".format(self._pin, self.input(), not self.input()))
        self._underlying.toggle()

    def set_pulse_width(self, delay):
        self._pulse_width = delay

    def pulse(self, delay_ms=250):
        logging.getLogger("Launch").getChild("Tools.Pin").debug("pulse({}, {}ms)".format(self._pin, delay_ms))
        self._underlying.blink( on_time=delay_ms/1000, off_time=delay_ms/1000, n=1, background=False)

    def input(self) -> bool:
        if self._direction == PinDirection.OUT:
            return self._underlying.value
        return self._underlying.value

    def output(self, val: bool):
        self._out = val
        if self._direction == PinDirection.OUT:
            self._underlying.value = val

    def get_direction(self):
        return self._direction

    def set_detect(self, callback, level: PinEventEdge):
        if level == PinEventEdge.RISING:
            self._underlying.when_pressed = callback
        elif level == PinEventEdge.FALLING:
            self._underlying.when_released = callback
        elif level == PinEventEdge.BOTH:
            self._underlying.when_released = callback
            self._underlying.when_pressed = callback

