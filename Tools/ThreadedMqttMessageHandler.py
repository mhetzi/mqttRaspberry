# -*- coding: utf-8 -*-
import paho.mqtt.client as mclient
import logging
import threading as thr
import queue

class MqttMessageThread(thr.Thread):

    def __init__(self, client: mclient.Client, topic: str, callback, logger: logging.Logger, QOS=0):
        super().__init__()
        if not callable(callback):
            raise AttributeError("callback muss aufrufbar sein.")
        self.setName("MsgThr")
        self.setDaemon(False)
        self._cancel_new_when_running = False
        self._sleeping = True
        self._callback = callback
        self._message_queue = queue.Queue()
        self._logger = logger.getChild("mmThread-{}".format(topic))
        self._mutex = thr.Lock()
        self.start()
        client.subscribe(topic, qos=QOS)
        client.message_callback_add(topic, self.__mqtt_callback)
        self._kill = False

    def kill(self):
        with self._mutex:
            self._kill = True
        self.join()

    def set_cancel_new_while_running(self, val: bool):
        """
        Nachrichten verwerfen wenn die Ausführung nicht beendet wurde.
        :param val: Verwerfen? Standart Nein
        :return: Nichts
        """
        self._cancel_new_when_running = val

    def __mqtt_callback(self, client, userdata, message: mclient.MQTTMessage):
        with self._mutex:
            if self._cancel_new_when_running and not self._sleeping:
                self._logger.debug("Ignoriere neue Nachricht, handler ist noch beschäftigt.")
                return
        self._message_queue.put([client, userdata, message], block=True, timeout=14)

    def run(self):
        while True:
            try:
                qi = self._message_queue.get(block=True, timeout=5)
                with self._mutex:
                    self._sleeping = False
                try:
                    self._callback(qi[0], qi[1], qi[2])
                except Exception as x:
                    self._logger.exception("Callback hat eine Ausnahme verursacht!")
                self._logger.debug("Neue Nachricht verarbeitet.")
                with self._mutex:
                    self._sleeping = True
                    if self._kill:
                        return
            except queue.Empty:
                with self._mutex:
                    if self._kill:
                        return
