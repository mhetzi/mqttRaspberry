# -*- coding: utf-8 -*-

import paho.mqtt.client as mclient

import Tools.Config as conf
import logging
import threading
import os
import errno
import json


class PluginLoader:

    @staticmethod
    def getConfigKey():
        return "JsonPipe"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return JsonPipe(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        conf["JsonPipe/Path"] = ConsoleInputTools.get_input("Pfad zur namedpipe angeben. (Pipe muss nicht vorhanden sein.)", True)


class JsonPipe(threading.Thread):

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        threading.Thread.__init__(self)
        self.__client = client
        self.__logger = logger.getChild("JsonPipeReader")
        self._config = opts
        self._pins = []
        self._device_id = device_id
        self.setName("JsonPipeReader")
        self._doExit = False

    def register(self):
        self.start()

    def stop(self):
        self._doExit = True
        with open(self._config.get("JsonPipe/Path", None), mode="w") as fifo:
            fifo.write("kill")

    def run(self):
        try:
            os.mkfifo(self._config.get("JsonPipe/Path", None))
        except OSError as oe:
            if oe.errno != errno.EEXIST:
                raise

        while not self._doExit:
            self.__logger.debug("Warte auf FIFO...")
            with open(self._config.get("JsonPipe/Path", None)) as fifo:
                self.__logger.debug("FIFO geöffnet.")
                while not self._doExit:
                    data = fifo.read()
                    if len(data) == 0:
                        self.__logger.debug("FIFI gegenstelle geschlossen.")
                        break
                    self.__logger.debug('Read: "{0}"'.format(data))
                    try:
                        d = json.loads(data)
                        self.__client.publish(d["t"], d["p"], d.get("r", False))
                    except json.decoder.JSONDecodeError:
                        self.__logger.error("Json konnte nicht dekodiert werden.")
