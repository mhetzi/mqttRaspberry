# -*- coding: utf-8 -*-

from PIL import Image, ImageDraw
import math
import random
import threading
import queue
import numpy as np
import io
import schedule

try:
    import picamera as cam
    import picamera.array as cama
except ImportError:
    import Mods.referenz.picamera.picamera as cam
    import Mods.referenz.picamera.picamera.array as cama

from PIL import Image, ImageDraw, ImageFont, ImageStat

import pyximport
pyximport.install()
import Mods.PiCameraMotion.analyze.hotblock
from Tools.Config import PluginConfig


class Analyzer(cama.PiAnalysisOutput):
    processed = 0
    states = {"motion_frames": 0, "still_frames": 0,
              "noise_count": 0, "hotest": [], "zmdata": ""}
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
    _shed_task = None

    def motion_call(self, motion: bool, data: dict, wasMeassureing: bool):
        self.logger.error("motion_call nicht überschrieben!")

    def motion_data_call(self, data: dict):
        self.logger.error("motion_data_call nicht überschrieben!")

    def pil_magnitude_save_call(self, img: Image.Image, data: dict):
        self.logger.error("pil_magnitude_save_call nicht überschrieben")

    def cal_getMjpeg_Frame(self):
        raise NotImplementedError()

    def __init__(self, camera, size=None, logger=None, config=None):
        super(Analyzer, self).__init__(camera, size)
        self.cols = None
        self.rows = None
        self.logger = logger
        self.logger.debug("Queue wird erstellt...")
        self._queue = queue.Queue(10)
        self.disableAnalyzing = False
        self.config = config
        self._shed_task = schedule.every(15).seconds
        self._shed_task.do(self.laodZeroMap)

    def write(self, b):
        result = super(Analyzer, self).write(b)
        if self.cols is None:
            width, height = self.size or self.camera.resolution
            self.cols = ((width + 15) // 16) + 1
            self.rows = (height + 15) // 16
            if self.zeromap_py["enabled"]:
                self.logger.debug("Erstelle C Object for zeroMap...")
                self.__zeromap_data = Mods.PiCameraMotion.analyze.hotblock.ZeroMap(self.rows, self.cols)
                self.laodZeroMap()
        self.analyze(
            np.frombuffer(b, dtype=cama.motion_dtype).
            reshape((self.rows, self.cols)))
        return result

    def laodZeroMap(self):
        cb = self.brightness()
        if cb == -1:
            return
        ll = self.config.get("ranges", None)
        if ll is None or self.__zeromap_data is None:
            return
        if len(ll) < 1:
            return
        if self.zeromap_py["isBuilding"]:
            return
        found = min(ll, key=lambda x: abs(Analyzer.getMin(x[0], x[1], cb) - cb) )
        if found[2] != self.states["zmdata"]:
            f,n = self.config.getIndependendFile(found[2])
            d = f["pimotion/data"]
            self.logger.debug("Lade Savedata in C zeroMap von {}".format(n))
            self.__zeromap_data.loadZeroMap(d)
            self.states["zmdata"] = found[2]
            self.states["lowest_brightness"] = found[0]
            self.states["highest_brightness"] = found[1]
            f.stop()

    @staticmethod
    def getMin(v1, v2, n):
        return min([v1, v2], key=lambda x: abs(x-n))

    @staticmethod
    def getNumber(val):
        try:
            return int(val)
        except ValueError:
            return -100000000000

    def analyze(self, a: cama.motion_dtype):
        if self.disableAnalyzing:
            return
        if self.zeromap_py["enabled"] and self.__zeromap_data != None and not self.zeromap_py["isBuilding"]:
            a = self.__zeromap_data.subtractMask(a)
        hottestBlock = Mods.PiCameraMotion.analyze.hotblock.hotBlock(
            a, self.rows, self.cols, self.blockMinNoise)
        try:
            self._queue.put_nowait((hottestBlock, a))
        except queue.Full:
            self.logger.debug("Queue ist voll")

    def trainZeroMap(self, update=False):
        self.logger.debug("Erstelle C Object for zeroMap...")
        if not update or self.__zeromap_data is None:
            self.__zeromap_data = Mods.PiCameraMotion.analyze.hotblock.ZeroMap(self.rows, self.cols)
        self.logger.info("Schalte zeroMap ein...")
        self.zeromap_py["enabled"] = True
        self.logger.info("Schalte zeroMap Baustatus um...")
        self.zeromap_py["isBuilding"] = True
        self.framesToNoMotion *= 15
        if not update:
            self.states["lowest_brightness"] = 1000000
            self.states["highest_brightness"] = 0


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
    
    def brightness(self):
        frame = self.cal_getMjpeg_Frame()
        bio = None
        if frame is not None:
            try:
                bio = Image.open(io.BytesIO(frame))
            except:
                self.logger.exception("Erkennen der Helligkeit ist fehlgeschlagen")
                return -1
        else:
            self.logger.warning("Snapshot is None")
            return
        stat = ImageStat.Stat(bio)
        r,g,b = stat.mean
        return math.sqrt(0.299*(r**2) + 0.587*(g**2) + 0.114*(b**2))

    def __train_zero(self, a: cama.motion_dtype):
        if self.__zeromap_data is None:
            self.zeromap_py["isBuilding"] = False
            return
        #self.logger.debug("T")
        changed = self.__zeromap_data.trainZeroMap(a)
        still_pre_change = self.states["still_frames"]
        br = -1
        if changed:
            self.states["still_frames"] = 0
            self.states["motion_frames"] += 1
            if self.states.get("brightness_holdoff", 0) <= 0:
                br = self.brightness()
                if br > -1:
                    if self.states.get("lowest_brightness", 1000000) > br:
                        self.states["lowest_brightness"] = br
                    if self.states.get("highest_brightness", 0) < br:
                        self.states["highest_brightness"] = br
                self.states["brightness_holdoff"] = 60
            else:
                self.states["brightness_holdoff"] -= 1

        else:
            self.states["still_frames"] += 1
            self.states["motion_frames"] = 0

        self.logger.debug("TZ C:{} still: {} motion:{} brightness: {}".format(
            "TRUE " if changed else "FALSE",
            self.states["still_frames"],
            self.states["motion_frames"],
            br))

        if self.states["motion_frames"] > 0 and still_pre_change > self.framesToNoMotion:
            self.motion_call(True, self.states, False)
        elif self.states["still_frames"] == self.framesToNoMotion:
            self.motion_call(False, self.states, False)

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
                self.framesToNoMotion *= 15

            while True:
                hottestBlock, a = self._queue.get()
                if not self.__thread_do_run:
                    break
                self.processed += 1
                self.states["hotest"] = [hottestBlock[0],
                                        hottestBlock[1], hottestBlock[2]]
                self.states["noise_count"] = hottestBlock[3]
                self.states["object"] = hottestBlock

                if self.zeromap_py["isBuilding"]:
                    self.__train_zero(a)
                    #self.logger.debug("still_frame {} von {}".format(
                    #    self.states["still_frames"], self.framesToNoMotion))

                elif self.countMinNoise > hottestBlock[3] and self.countMaxNoise > hottestBlock[3] and hottestBlock[2] < self.blockMinNoise:
                    self.states["still_frames"] += 1
                    self.states["motion_frames"] = 0
                    #if self._calibration_running:
                    #    self.logger.debug("still_frame {} von {}".format(
                    #        self.states["still_frames"], self.framesToNoMotion))
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
                    self.framesToNoMotion = self.framesToNoMotion / 15
                    c, name = self.config.getIndependendFile(None)
                    c["pimotion/data"] = self.__zeromap_data.saveZeroMap()
                    c.save()
                    new_calib = [
                        self.states["lowest_brightness"],
                        self.states["highest_brightness"],
                        name
                    ]
                    self.logger.info("Füge {} der Config hinzu...".format(new_calib))
                    old_list = self.config.get("ranges", None)
                    self.logger.debug("alte Liste ist {}".format(old_list))
                    if not isinstance(old_list, list) or old_list is None:
                        old_list = []
                        self.logger.debug("Liste ist zurückgesetzt {}".format(old_list))
                    old_list.append(new_calib)
                    self.config["ranges"] = old_list
                    self.logger.debug("Neue Liste ist jetzt {}".format(self.config["ranges"]))
                    self.config.save()
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
                    self.framesToNoMotion = self.framesToNoMotion / 15
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
                            try:
                                self.laodZeroMap()
                            except:
                                self.logger.exception("Neuladen der Zeromap fehlgschlagen")
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
        self._queue.put_nowait((None, None))
        schedule.cancel_job(self._shed_task)
        self.config["zeroMap"] = zeromap_py
