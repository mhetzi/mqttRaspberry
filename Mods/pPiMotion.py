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
    logger = None
    processed = 0

    def analyze(self, a: cama.motion_dtype):
        self.hotBlock(a)
    
    def hotBlock(self, a):
        hottestBlock = [0,0,0]
        #print("   Columns    ")
        #print( list(range(0, len(a[0]))) )
        rows = len(a)
        for x in range(0, rows):
            row = a[x]
            cols = len(row)
            #print(x, end = ": ")
            for y in range(0, cols):
                col = row[y]
                hottness = col[2]
                if hottestBlock[2] < hottness:
                    hottestBlock = [x,y,hottness]
                    #print("H", end="")
                #print(hottness, end=" ")
            #print("")
        self.logger.info("(x,y,val) = (%d,%d,%d) ", hottestBlock[0],hottestBlock[1],hottestBlock[2])
        self.processed += 1


    def getTotalChanged(self, a):
        added = 0
        x = np.square(a['x'].astype(np.float))
        for xx in x:
            for xxx in xx:
                added += xxx
        y = np.square(a['y'].astype(np.float))
        for yy in y:
            for yyy in yy:
                added += yyy
        self.logger.info("Changed: %d", added)


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
                anal.logger = self.__logger.getChild("Analyzer")
                camera.start_recording(self._circularStream, format='h264', motion_output=anal)
                camera.start_recording(self._webStream, format='mjpeg', splitter_port=2)
                # Und jetzt einfach warten
                while not self._doExit:
                    try:
                        camera.wait_recording(5)
                        pps = anal.processed / 5
                        self.__logger.info("Pro Sekunde verarbeitet: %d", pps)
                    except:
                        self.__logger.exception("Kamera Fehler")
        camera.stop_recording(splitter_port=2)
        camera.stop_recording()

    def motion(self):
        if self._inMotion:
            return
        return
        
