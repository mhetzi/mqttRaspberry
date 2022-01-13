# -*- coding: utf-8 -*-
import logging

class EventListener:
    _logger = None
    _event_path = ""

    def __init__(self, logger:logging.Logger, event_path, broker):
        self._logger = logger.getChild("EventListener[{}]".format(event_path))
        self._event_path = event_path
        self._callback = lambda y: self._logger.warning("EventListener: {} hat kein Callback.".format(self._event_path))
        self._broker = broker

    def __call__(self, ev: str, extendet):
        self.checkAndFire(ev, extendet)

    def checkAndFire(self, ev: str, extendet):
        if ev == self._event_path:
            self.fire(extendet)

    def fire(self, extendet):
        try:
            self._callback(extendet)
        except TypeError:
            try:
                self._callback()
            except:
                self._logger.exception("Callback kann nicht ausgeführt werden!")

    def unsubscribe(self):
        self._broker.deregisterListener(self)

class EventBroker:
    _listeners = []

    def __init__(self, logger: logging.Logger):
        self._logger = logger.getChild("EventBroker")
    
    def registerListener(self, event_path: str, callback):
        if not callable(callback):
            raise ValueError("Callback is not callable")
        listener = EventListener(self._logger, event_path, self)
        listener._callback = callback
    
    def deregisterListener(self, listener);
        pass

