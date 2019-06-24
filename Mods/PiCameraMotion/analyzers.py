# -*- coding: utf-8 -*-

import numpy as np

try:
    import picamera as cam
    import picamera.array as cama
except ImportError:
    import Mods.referenz.picamera.picamera as cam
    import Mods.referenz.picamera.picamera.array as cama

import pyximport; pyximport.install()
import Mods.PiCameraMotion.analyze.hotblock
import queue
import threading

class Analyzer(cama.PiAnalysisOutput):
    processed = 0
    states = {"motion_frames": 0, "still_frames": 0, "noise_count": 0, "hotest": []}
    blockMaxNoise = 0
    countMinNoise = 0
    framesToNoMotion = 0
    frameToTriggerMotion = 0
    _calibration_running = False
    _thread = None
    __thread_do_run = True
    __max_ermittelt = False
    __min_ermittelt = False
    __motion_triggered = False

    def motion_call(self, motion:bool, data:dict, wasMeassureing:bool):
        self.logger.error("motion_call nicht überschrieben!")

    def motion_data_call(self, data:dict):
        self.logger.error("motion_data_call nicht überschrieben!")

    def __init__(self, camera, size=None, logger=None):
        super(Analyzer, self).__init__(camera, size)
        self.cols = None
        self.rows = None
        self.logger = logger
        self.logger.debug("Queue wird erstellt...")
        self._queue = queue.Queue(5)

    def write(self, b):
        result = super(Analyzer, self).write(b)
        if self.cols is None:
            width, height = self.size or self.camera.resolution
            self.cols = ((width + 15) // 16) + 1
            self.rows = (height + 15) // 16
        self.analyze(
                np.frombuffer(b, dtype=cama.motion_dtype).\
                reshape((self.rows, self.cols)))
        return result

    def analyze(self, a: cama.motion_dtype):
        hottestBlock = Mods.PiCameraMotion.analyze.hotblock.hotBlock(a, self.rows, self.cols, self.blockMaxNoise)
        try:
            self._queue.put_nowait(hottestBlock)
        except queue.Full:
            self.logger.debug("Queue ist voll")
    
    def thread_queue_reader(self):
        import random
        import math
        for _ in range(6):
            try:
                self._queue.get_nowait()
            except queue.Empty:
                self.logger.debug("Queue ist leer")
        self.logger.debug("QueueReader läuft")
        if self.blockMaxNoise < 0 and self.countMinNoise < 0:
            self._calibration_running = True
            self.blockMaxNoise = 0
            self.framesToNoMotion *= 10
        while self.__thread_do_run:
            hottestBlock = self._queue.get()
            if self._calibration_running:
                if self.countMinNoise <= hottestBlock[3]:
                    if self.states["motion_frames"] >= self.frameToTriggerMotion:
                        add = math.floor( (hottestBlock[3] - self.blockMaxNoise ) / 1.25 )
                        self.countMinNoise += add if add >= 2 else 2
                        if random.randrange(0, 100) < 25:
                            self.blockMaxNoise -= 35
                            if self.blockMaxNoise < 0:
                                self.blockMaxNoise = 0
                        self.states["still_frames"] = 0
                        self.states["motion_frames"] = 0
                        self.logger.info("Kalibriere derzeit bei {} +countMinNoise".format(self.countMinNoise))
                    else:
                        self.states["motion_frames"] += 1
                if hottestBlock[2] >= self.blockMaxNoise and self.states["motion_frames"] >= self.frameToTriggerMotion:
                    #self.logger.info("(x,y,val,count) = (%d,%d,%d,%d) ", hottestBlock[0], hottestBlock[1], hottestBlock[2], hottestBlock[3])
                    if self.states["motion_frames"] >= self.frameToTriggerMotion:
                        add = math.floor( (hottestBlock[2] - self.blockMaxNoise ) / 5 )
                        self.blockMaxNoise += add if add >= 2 else 2
                        if random.randrange(0, 100) < 25:
                            self.countMinNoise -= 2
                            if self.countMinNoise < 0:
                                self.countMinNoise = 0
                        self.states["still_frames"] = 0
                        self.states["motion_frames"] = 0
                        self.logger.info("Kalibriere derzeit bei {} +blockNoise".format(self.blockMaxNoise))
                    else:
                        self.states["motion_frames"] += 1
            if self.countMinNoise > hottestBlock[3] and hottestBlock[2] < self.blockMaxNoise:
                self.states["still_frames"] += 1
                self.states["motion_frames"] = 0
                if self._calibration_running:
                    self.logger.debug("still_frame {} von {}".format( self.states["still_frames"], self.framesToNoMotion))
            else:
                self.states["motion_frames"] += 1
                self.logger.debug("Bewegung! {} von {}".format(self.states["motion_frames"], self.frameToTriggerMotion))
            self.processed += 1
            self.states["hotest"] = [hottestBlock[0], hottestBlock[1], hottestBlock[2]]
            self.states["noise_count"] = hottestBlock[3]

            if self._calibration_running and self.states["still_frames"] > self.framesToNoMotion:
                #import math
                #self.blockMaxNoise = math.ceil(self.blockMaxNoise / 100 * 130)
                try:
                    self.motion_call(False, self.states, True)
                except:
                    pass
                self._calibration_running = False
                self.logger.info("Die ermittelten Werte block {} count {}".format(self.blockMaxNoise, self.countMinNoise))
                self.framesToNoMotion = self.framesToNoMotion / 10
            elif not self._calibration_running:
                try:
                    if self.states["noise_count"] >= self.countMinNoise or self.states["hotest"][2] > self.blockMaxNoise:
                        self.motion_data_call(self.states)
                except Exception as e:
                    self.logger.exception("Motion data call Exception: {}".format(str(e)))
                try:
                    if self.states["motion_frames"] >= self.frameToTriggerMotion and not self.__motion_triggered:
                        self.logger.debug("Trigger Motion")
                        self.states["still_frames"] = 0
                        self.states["motion_frames"] = 0
                        self.motion_call(True, self.states, False)
                        self.logger.debug("motion_call called")
                        self.__motion_triggered = True
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
                    self.logger.exception("Motion call Exception: {}".format(str(e)))
        self.logger.debug("QueueReader geht schlafe (für immer)")

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
        #self.logger.info("(x,y,val) = (%d,%d,%d) ", hottestBlock[0],hottestBlock[1],hottestBlock[2])
        self.processed += 1

    def run_queue(self):
        self.logger.debug("Queue Thread wird erstellt...")
        self._thread = threading.Thread(target=lambda: self.thread_queue_reader(), name="Analyzer Thread")
        self.logger.debug("Queue Thread wird gestartet...")
        self._thread.run()

    def stop_queue(self):
        self.__thread_do_run = False

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
