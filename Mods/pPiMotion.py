import numpy as np
try:
    import picamera as cam
    import picamera.array as cama
except ImportError:
    import Mods.referenz.picamera.picamera as cam
    import Mods.referenz.picamera.picamera.array as cama
 
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
        return "PiMotion"

    @staticmethod
    def getPlugin(client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        return PiMotionMain(client, opts, logger, device_id)

    @staticmethod
    def runConfig(conf: conf.BasicConfig, logger:logging.Logger):
        from Tools import ConsoleInputTools
        conf["PiMotion/camera/width"] = ConsoleInputTools.get_number_input("Resolution width", 640)
        conf["PiMotion/camera/height"] = ConsoleInputTools.get_number_input("Resolution height", 480)
        conf["PiMotion/camera/fps"] = ConsoleInputTools.get_number_input("Framerate", 25)
        print("")
        conf["PiMotion/motion/recordPre"] = ConsoleInputTools.get_number_input("Sekunden vor Bwegung aufnehmen", 1)
        conf["PiMotion/motion/recordPost"] = ConsoleInputTools.get_number_input("Sekunden nach Bwegung aufnehmen", 1)


class NullOutput(object):
    def __init__(self):
        self.size = 0

    def write(self, s):
        self.size += len(s)

    def flush(self):
        print('%d bytes would have been written' % self.size)

    def reset(self):
        self.size = 0

class Analyzer(cama.PiMotionAnalysis):
    motion_call = None
    def analyze(self, a):
        print("DATA")
        print(a)
        print("END")
        a = np.sqrt(
            np.square(a['x'].astype(np.float)) +
            np.square(a['y'].astype(np.float))
            ).clip(0, 255).astype(np.uint8)
        #If there're more than 10 vectors with a magnitude greater
        #than 60, then say we've detected motion
        if (a > 60).sum() > 10:
            print('Motion detected!')
            if callable(self.motion_call):
                self.motion_call()

class PiMotionMain(threading.Thread):

    _motionStream = NullOutput()
    _webStream = NullOutput()
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

            with Analyzer(camera) as anal:
                anal.motion_call = self.motion
                camera.start_recording(self._circularStream, format='h264', motion_output=anal)
                camera.start_recording(self._webStream, format='mjpeg', splitter_port=2)
                # Und jetzt einfach warten
                while not self._doExit:
                    try:
                        camera.wait_recording(30)
                    except:
                        self.__logger.exception("Kamera Fehler")
        camera.stop_recording()
        camera.stop_recording(splitter_port=2)

    def motion(self):
        if self._inMotion:
            return
        return
        
