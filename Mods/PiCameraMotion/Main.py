# -*- coding: utf-8 -*-

import paho.mqtt.client as mclient

import Tools.Config as conf
import logging

import numpy as np
try:
    import picamera as cam
    import picamera.array as cama
except ImportError:
    import Mods.referenz.picamera.picamera as cam
    import Mods.referenz.picamera.picamera.array as cama


import threading
import Mods.PiCameraMotion.etc as etc
import Mods.PiCameraMotion.http as httpc
import pyximport; pyximport.install()
import Mods.PiCameraMotion.analyzers as analyzers

class PiMotionMain(threading.Thread):

    _motionStream = etc.NullOutput()
    _webStream = etc.NullOutput()
    _circularStream = None
    _inMotion = False

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        threading.Thread.__init__(self)
        self.__client = client
        self.__logger = logger.getChild("PiMotion")
        self._config = opts
        self._device_id = device_id

        self.setName("PiCamera")
        self._doExit = False

    def register(self):
        # Setup MQTT zeug
        # Starte thread
        self.start()

    def stop(self):
        self._doExit = True

    def run(self):
        with cam.PiCamera() as camera:
            # Init Kamera
            camera.resolution = (self._config["PiMotion/camera/width"], self._config["PiMotion/camera/height"])
            self._circularStream = cam.PiCameraCircularIO(camera, seconds=self._config["PiMotion/motion/recordPre"])

            with analyzers.Analyzer(camera) as anal:
                anal.motion_call = self.motion
                anal.logger = self.__logger.getChild("Analyzer")
                camera.start_recording(self._circularStream, format='h264', motion_output=anal)

                if self._config.get("PiMotion/http/enabled", False):
                    http_out = httpc.StreamingOutput()
                    address = (
                        self._config.get("PiMotion/http/addr","127.0.0.1"),
                        self._config.get("PiMotion/http/port",8083)
                    )
                    server = httpc.StreamingServer(address, httpc.makeStreamingHandler(http_out))
                    server.start()
                    camera.start_recording(self._webStream, format='mjpeg', splitter_port=2)
                # Und jetzt einfach warten
                while not self._doExit:
                    try:
                        camera.wait_recording(5)
                        pps = anal.processed / 5
                        anal.processed = 0
                        self.__logger.debug("Pro Sekunde verarbeitet: %d", pps)
                    except:
                        self.__logger.exception("Kamera Fehler")
                        exit(-1)
        server.server_close()
        camera.stop_recording(splitter_port=2)
        camera.stop_recording()

    def motion(self):
        if self._inMotion:
            return
        return
        