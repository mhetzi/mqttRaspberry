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
    __block_mask = {"enabled": False, "mask": None,
                    "isBuilding": False, "cObj": None}

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
        self.analyze(
            np.frombuffer(b, dtype=cama.motion_dtype).
            reshape((self.rows, self.cols)))
        return result

    def analyze(self, a: cama.motion_dtype):
        cMask = None
        if self.__block_mask["enabled"] and self.__block_mask["cObj"] is not None:
            cMask = self.__block_mask["cObj"]
        hottestBlock = Mods.PiCameraMotion.analyze.hotblock.hotBlock(
            a, self.rows, self.cols, self.blockMinNoise, cMask)
        try:
            self._queue.put_nowait((hottestBlock, a))
        except queue.Full:
            self.logger.debug("Queue ist voll")

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

    def __prepare_block_mask_data(self):
        if self.rows is None or self.cols is None:
            return False
        if self.__block_mask["mask"] is None:
            self.logger.debug("Build Mask dict")
            self.__block_mask["mask"] = []
            for _ in range(self.rows):
                col = []
                for __ in range(self.cols):
                    col.append(0)
                self.__block_mask["mask"].append(col)
            self.__block_mask["cObj"] = Mods.PiCameraMotion.analyze.hotblock.init_block_mask(
                self.rows, self.cols)
            return True
        elif self.__block_mask["mask"] is not None and self.__block_mask["cObj"] is None:
            try:
                if not isinstance(self.__block_mask["mask"], list):
                    self.logger.warning("Mask Object ist von Typ {} sollte aber list sein".format(
                        type(self.__block_mask["mask"])))
                    raise TypeError()
                self.__block_mask["cObj"] = Mods.PiCameraMotion.analyze.hotblock.build_block_mask(
                    self.__block_mask["mask"],
                    self.rows,
                    self.cols
                )
                return True
            except TypeError as e:
                self.__block_mask["mask"] = None
                self.__block_mask["cObj"] = None
                self.logger.warning(
                    "TypeError( {} ) on build_block_mask resetting...".format(str(e)))
                return False
        return True

    def __build_block_mask(self, hottestBlock):
        if not self.__prepare_block_mask_data():
            self.logger.warning("__prepare_block_mask_data error.")
            return
        x = hottestBlock[0]
        y = hottestBlock[1]
        sad = hottestBlock[2]
        if self.__block_mask["mask"][x][y] < sad:
            self.__block_mask["mask"][x][y] = sad
            self.logger.debug(
                "x: {}, y: {} auf minimal {} gesetzt".format(x, y, sad))
            self.__block_mask["cObj"] = Mods.PiCameraMotion.analyze.hotblock.update_block_mask(
                hottestBlock[4], self.__block_mask["cObj"])

    def enable_blockmask(self, mask, on=True, build_new=False):
        if mask is not None:
            self.__block_mask["mask"] = mask
        else:
            self.__block_mask["mask"] = []
        self.__block_mask["enabled"] = on
        self.__block_mask["isBuilding"] = build_new
        self.__prepare_block_mask_data()

    def get_blockmask_enabled(self):
        return self.__block_mask["enabled"], self.__block_mask["mask"], self.__block_mask["isBuilding"]

    def thread_queue_reader(self):
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
            if self.countMinNoise > hottestBlock[3] and self.countMaxNoise > hottestBlock[3] and hottestBlock[2] < self.blockMinNoise:
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
                if self.__block_mask["isBuilding"]:
                    self.__build_block_mask(hottestBlock)
                try:
                    if self.states["motion_frames"] >= self.frameToTriggerMotion and not self.__motion_triggered:
                        self.pil_magnitude_save_call(a, self.__old_States)
                        self.pil_magnitude_save_call(a, self.states)
                    else:
                        self.__old_States = copy.deepcopy(self.states)
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

    def run_queue(self):
        self.logger.debug("Queue Thread wird erstellt...")
        self._thread = threading.Thread(
            target=lambda: self.thread_queue_reader(), name="Analyzer Thread")
        self.logger.debug("Queue Thread wird gestartet...")
        self._thread.run()

    def stop_queue(self):
        self.__thread_do_run = False
