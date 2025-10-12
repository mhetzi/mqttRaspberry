# -*- coding: utf-8 -*-

import paho.mqtt.client as mclient

import Tools.Config as conf
import logging
import threading
import os
import errno
import json

from Tools import PluginManager

class PluginLoader(PluginManager.PluginLoader):

    @staticmethod
    def getConfigKey():
        return "JsonPipe"

    @staticmethod
    def getPlugin(opts: conf.BasicConfig, logger: logging.Logger):
        return JsonPipe(opts, logger)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        conf["JsonPipe/Path"] = ConsoleInputTools.get_input("Pfad zur namedpipe angeben. (Pipe muss nicht vorhanden sein.)", True)
    
    @staticmethod
    def getNeededPipModules() -> list[str]:
        return []


class JsonPipe(threading.Thread, PluginManager.PluginInterface):

    def __init__(self, opts: conf.BasicConfig, logger: logging.Logger):
        threading.Thread.__init__(self)
        self.__logger = logger.getChild("JsonPipeReader")
        self._config = opts
        self._pins = []
        self.name = "JsonPipeReader"
        self._doExit = False
        self._lastData = None

    def register(self, was_connected=False):
        if not was_connected:
            self.start()

    def stop(self):
        self._doExit = True
        with open(self._config.get("JsonPipe/Path", None), mode="w") as fifo:
            fifo.write("kill")

    def run(self):
        while not self._doExit:
            try:
                os.mkfifo(self._config.get("JsonPipe/Path", None))
                os.chmod(self._config.get("JsonPipe/Path", None), 0o0666)
            except OSError as oe:
                if oe.errno != errno.EEXIST:
                    os.remove(self._config.get("JsonPipe/Path", None))
                    try:
                        os.mkfifo(self._config.get("JsonPipe/Path", None))
                        os.chmod(self._config.get("JsonPipe/Path", None), 0o0666)
                    except OSError as oe:
                        if oe.errno != errno.EEXIST:
                            self.__logger.info("Namedpipe konnte nicht erstellt werden")
#            self.__logger.debug("Warte auf FIFO...")
            with open(self._config.get("JsonPipe/Path", None)) as fifo:
#                self.__logger.debug("FIFO geöffnet.")
                while not self._doExit:
                    data = fifo.read()
                    if len(data) == 0:
#                        self.__logger.debug("FIFI gegenstelle geschlossen.")
                        break
                    if data == self._lastData:
                        continue
                    self._lastData = data
                    self.__logger.debug('Read: "{0}"'.format(data))
                    if data == "kill" and self._doExit:
                        return
                    try:
                        d = json.loads(data)
                        self._pluginManager._client.publish(d["t"], d["p"], d.get("r", False))
                    except json.decoder.JSONDecodeError:
                        self.__logger.error("Json konnte nicht dekodiert werden.")
        os.remove(self._config.get("JsonPipe/Path", None))
        self.__logger.info("Lese Thread stirbt gerade")

    def sendStates(self):
        try:
            d = json.loads(self._lastData)
            self._pluginManager._client.publish(d["t"], d["p"], d.get("r", False))
        except json.decoder.JSONDecodeError:
            self.__logger.error("Json konnte nicht dekodiert werden.")
