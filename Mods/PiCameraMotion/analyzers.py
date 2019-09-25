# -*- coding: utf-8 -*-

from PIL import Image, ImageDraw
import math
import random
import threading
import queue
import numpy as np

try:
    import picamera as cam
    import picamera.array as cama
except ImportError:
    import Mods.referenz.picamera.picamera as cam
    import Mods.referenz.picamera.picamera.array as cama

import pyximport
pyximport.install()
import Mods.PiCameraMotion.analyze.hotblock


class Analyzer(cama.PiAnalysisOutput):
    processed = 0
    states = {"motion_frames": 0, "still_frames": 0,
              "noise_count": 0, "hotest": []}
    __old_States = None
    blockMinNoise = 0
    countMinNoise = 0
    countMaxNoise = -1
    framesToNoMotion = 0
    frameToTriggerMotion = 0
    _calibration_running = False
    _thread = None
    __thread_do_run = True
    __max_ermittelt = False
    __min_ermittelt = False
    __motion_triggered = False
    zeromap_py = {"enabled": False, "isBuilding": False, "dict": None}
    __zeromap_data = None

    def motion_call(self, motion: bool, data: dict, wasMeassureing: bool):
        self.logger.error("motion_call nicht überschrieben!")

    def motion_data_call(self, data: dict):
        self.logger.error("motion_data_call nicht überschrieben!")

    def pil_magnitude_save_call(self, img: Image.Image, data: dict):
        self.logger.error("pil_magnitude_save_call nicht überschrieben")

    def __init__(self, camera, size=None, logger=None):
        super(Analyzer, self).__init__(camera, size)
        self.cols = None
        self.rows = None
        self.logger = logger
        self.logger.debug("Queue wird erstellt...")
        self._queue = queue.Queue(2)

    def write(self, b):
        result = super(Analyzer, self).write(b)
        if self.cols is None:
            width, height = self.size or self.camera.resolution
            self.cols = ((width + 15) // 16) + 1
            self.rows = (height + 15) // 16
            if self.zeromap_py["enabled"]:
                self.logger.debug("Erstelle C Object for zeroMap...")
                self.__zeromap_data = Mods.PiCameraMotion.analyze.hotblock.ZeroMap(self.rows, self.cols)
            if self.zeromap_py["dict"] is not None and self.__zeromap_data is not None:
                self.logger.debug("Lade Savedata in C zeroMap...")
                self.__zeromap_data.loadZeroMap(self.zeromap_py["dict"])
        self.analyze(
            np.frombuffer(b, dtype=cama.motion_dtype).
            reshape((self.rows, self.cols)))
        return result

    def analyze(self, a: cama.motion_dtype):
        if self.zeromap_py["enabled"] and self.__zeromap_data != None and not self.zeromap_py["isBuilding"]:
            a = self.__zeromap_data.subtractMask(a)
        hottestBlock = Mods.PiCameraMotion.analyze.hotblock.hotBlock(
            a, self.rows, self.cols, self.blockMinNoise)
        try:
            self._queue.put_nowait((hottestBlock, a))
        except queue.Full:
            self.logger.debug("Queue ist voll")

    def trainZeroMap(self):
        self.logger.debug("Erstelle C Object for zeroMap...")
        if self.__zeromap_data is None:
            self.__zeromap_data = Mods.PiCameraMotion.analyze.hotblock.ZeroMap(self.rows, self.cols)
        self.logger.info("Schalte zeroMap ein...")
        self.zeromap_py["enabled"] = True
        self.logger.info("Schalte zeroMap Baustatus um...")
        self.zeromap_py["isBuilding"] = True
        self.framesToNoMotion *= 10


    def __calibrate(self, hottestBlock: dict):
        if self.countMinNoise <= hottestBlock[3] and self.states["motion_frames"] >= self.frameToTriggerMotion:
            add = math.floor((hottestBlock[3] - self.blockMinNoise) / 1.25)
            self.countMinNoise += add if add >= 2 else 2
            if random.randrange(0, 100) < 25:
                self.blockMinNoise -= 35
                if self.blockMinNoise < 0:
                    self.blockMinNoise = 0
            self.states["still_frames"] = 0
            self.states["motion_frames"] = 0
            self.logger.info(
                "Kalibriere derzeit bei {} +countMinNoise".format(self.countMinNoise))
        if hottestBlock[2] >= self.blockMinNoise and self.states["motion_frames"] >= self.frameToTriggerMotion:
            add = math.floor((hottestBlock[2] - self.blockMinNoise) / 5)
            self.blockMinNoise += add if add >= 2 else 2
            if random.randrange(0, 100) < 25:
                self.countMinNoise -= 2
                if self.countMinNoise < 0:
                    self.countMinNoise = 0
            self.states["still_frames"] = 0
            self.states["motion_frames"] = 0
            self.logger.info(
                "Kalibriere derzeit bei {} +blockNoise".format(self.blockMinNoise))
    
    def __train_zero(self, a: cama.motion_dtype):
        if self.__zeromap_data is None:
            self.zeromap_py["isBuilding"] = False
            return
        self.logger.debug("T")
        changed = self.__zeromap_data.trainZeroMap(a)
        still_pre_change = self.states["still_frames"]
        if changed:
            self.states["still_frames"] = 0
            self.states["motion_frames"] += 1
        else:
            self.states["still_frames"] += 1
            self.states["motion_frames"] = 0
        
        if self.states["motion_frames"] > 0 and still_pre_change > self.framesToNoMotion / 10:
            self.motion_call(True, self.states, False)
        elif self.states["still_frames"] == self.framesToNoMotion / 10:
            self.motion_call(False, self.states, False)

        self.logger.debug("TZ C:{} still: {} motion:{}".format(changed, self.states["still_frames"], self.states["motion_frames"]))

    def thread_queue_reader(self):
        try:
            import copy
            for _ in range(6):
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    self.logger.debug("Queue ist leer")
            self.logger.debug("QueueReader läuft")
            if self.blockMinNoise < 0 and self.countMinNoise < 0:
                self._calibration_running = True
                self.blockMinNoise = 0
                self.framesToNoMotion *= 10

            while self.__thread_do_run:
                hottestBlock, a = self._queue.get()
                self.processed += 1
                self.states["hotest"] = [hottestBlock[0],
                                        hottestBlock[1], hottestBlock[2]]
                self.states["noise_count"] = hottestBlock[3]
                self.states["object"] = hottestBlock

                if self.zeromap_py["isBuilding"]:
                    self.__train_zero(a)
                    self.logger.debug("still_frame {} von {}".format(
                        self.states["still_frames"], self.framesToNoMotion))

                elif self.countMinNoise > hottestBlock[3] and self.countMaxNoise > hottestBlock[3] and hottestBlock[2] < self.blockMinNoise:
                    self.states["still_frames"] += 1
                    self.states["motion_frames"] = 0
                    if self._calibration_running:
                        self.logger.debug("still_frame {} von {}".format(
                            self.states["still_frames"], self.framesToNoMotion))
                else:
                    self.states["motion_frames"] += 1
                    #self.logger.debug("Bewegung! {} von {}".format(
                    #    self.states["motion_frames"], self.frameToTriggerMotion))
                    if self._calibration_running:
                        self.__calibrate(hottestBlock)
                    try:
                        if self.states["motion_frames"] >= self.frameToTriggerMotion and not self.__motion_triggered:
                            self.pil_magnitude_save_call(a, self.__old_States)
                            self.pil_magnitude_save_call(a, self.states)
                        else:
                            self.__old_States = copy.deepcopy(self.states)
                    except:
                        pass
                if self.zeromap_py["isBuilding"] and self.states["still_frames"] > self.framesToNoMotion:
                    self.zeromap_py["isBuilding"] = False
                    self.logger.info("ZeroMap gebaut. Sicherung wird erstellt")
                    self.framesToNoMotion = self.framesToNoMotion / 10
                    self.zeromap_py["dict"] = self.__zeromap_data.saveZeroMap()
                    try:
                        self.motion_call(False, self.states, True)
                    except:
                        pass

                if self._calibration_running and self.states["still_frames"] > self.framesToNoMotion:
                    try:
                        self.motion_call(False, self.states, True)
                    except:
                        pass
                    self._calibration_running = False
                    self.logger.info("Die ermittelten Werte block {} count {}".format(
                        self.blockMinNoise, self.countMinNoise))
                    self.framesToNoMotion = self.framesToNoMotion / 10
                elif not self._calibration_running:
                    try:
                        if self.states["noise_count"] >= self.countMinNoise or self.states["hotest"][2] > self.blockMinNoise:
                            self.motion_data_call(self.states)
                    except Exception as e:
                        self.logger.exception(
                            "Motion data call Exception: {}".format(str(e)))
                    try:
                        if self.states["motion_frames"] >= self.frameToTriggerMotion and not self.__motion_triggered:
                            self.__motion_triggered = True
                            self.logger.debug("Trigger Motion")
                            self.states["still_frames"] = 0
                            self.states["motion_frames"] = 0
                            self.motion_call(True, self.states, False)
                            self.logger.debug("motion_call called")
                        elif self.states["motion_frames"] >= self.frameToTriggerMotion and self.__motion_triggered:
                            self.states["still_frames"] = 0
                            self.states["motion_frames"] = 0
                        elif self.states["still_frames"] >= self.framesToNoMotion and self.__motion_triggered:
                            self.logger.debug("Detrigger Motion")
                            self.states["motion_frames"] = 0
                            self.motion_call(False, self.states, False)
                            self.logger.debug("motion_call called")
                            self.__motion_triggered = False
                    except Exception as e:
                        self.logger.exception(
                            "Motion call Exception: {}".format(str(e)))
            self.logger.debug("QueueReader geht schlafe (für immer)")
        except:
            self.logger.exception("QueueReader geht schlafen (Exception)")

    def run_queue(self):
        self.logger.debug("Queue Thread wird erstellt...")
        self._thread = threading.Thread(
            target=lambda: self.thread_queue_reader(), name="Analyzer Thread")
        self.logger.debug("Queue Thread wird gestartet...")
        self._thread.start()

    def stop_queue(self):
        self.__thread_do_run = False
        if self.__zeromap_data is not None:
            self.zeromap_py["dict"] = self.__zeromap_data.saveZeroMap()
