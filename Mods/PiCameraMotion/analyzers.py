# -*- coding: utf-8 -*-

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
import Mods.PiCameraMotion.analyze.motion
from Tools.Config import PluginConfig

class Analyzer(cama.PiAnalysisOutput):
    processed = 0
    states = {"motion_frames": 0, "still_frames": 0,
              "noise_count": 0, "hotest": [], "zmdata": "",
              "extendet": "init",
              "brightness": -1, "lightDiff": -1,
              "type": "hotblock"}
    __old_States = None
    blockMinNoise = 0
    countMinNoise = 0
    countMaxNoise = -1
    framesToNoMotion = 0
    frameToTriggerMotion = 0
    lightDiffBlock = 0.0
    _calibration_running = False
    _thread = None
    __thread_do_run = True
    __max_ermittelt = False
    __min_ermittelt = False
    __motion_triggered = False
    zeromap_py = {"enabled": False, "isBuilding": False, "dict": None}
    __zeromap_data = None
    __zeromap_block_loader = False
    __zeromap_data_trainee_id = ""
    _shed_task = None

    _motion = None

    def motion_call(self, motion: bool, data: dict, wasMeassureing: bool):
        self.logger.error("motion_call nicht überschrieben!")

    def motion_data_call(self, data: dict, changed:bool):
        self.logger.error("motion_data_call nicht überschrieben!")

    def pil_magnitude_save_call(self, img: Image.Image, data: dict):
        self.logger.error("pil_magnitude_save_call nicht überschrieben")

    def cal_getMjpeg_Frame(self):
        raise NotImplementedError()

    def __init__(self, camera, size=None, logger=None, config=None, fps=24, postSecs=1):
        super(Analyzer, self).__init__(camera, size)
        self.cols = None
        self.rows = None
        self.logger = logger
        self.logger.debug("Queue wird erstellt...")
        self._queue = queue.Queue(30)
        self.disableAnalyzing = False
        self.config = config
        self._shed_task = schedule.every(2).seconds
        self._shed_task.do(self.laodZeroMap)
        self._analyzer_lock = threading.Lock()
        self._on_hold = False
        self.__frame_drop = 0
        self._fps = fps
        self.postsecs = postSecs
        self._framecount = 0

    def write(self, b):
        result = super(Analyzer, self).write(b)
        if self._on_hold:
            return result
        if self.cols is None:
            width, height = self.size or self.camera.resolution
            self.cols = ((width + 15) // 16) + 1
            self.rows = (height + 15) // 16
            if self.zeromap_py["enabled"]:
                self.logger.debug("Erstelle C Object for zeroMap...")
                self.__zeromap_data = Mods.PiCameraMotion.analyze.hotblock.ZeroMap(self.rows, self.cols)
                self.__zeromap_data.activateLastFrame(True)
        self.analyze(
            np.frombuffer(b, dtype=cama.motion_dtype).
            reshape((self.rows, self.cols)))
        return result

    def saveZeroMap(self, isUpdate=False):
        self.zeromap_py["isBuilding"] = False
        self.logger.info("ZeroMap gebaut. Sicherung wird erstellt")
        if self.states.get("zmdata", None) is not None:
            c, name = self.config.getIndependendFile(name=self.states["zmdata"], no_watchdog=True, do_load=False)
            c.load(fileNotFoundOK=False)
            isUpdate = True
        else:
            c, name = self.config.getIndependendFile(name=None, no_watchdog=True)
        c["pimotion/data"] = self.__zeromap_data.saveZeroMap()
        c.save()
        if not isUpdate:
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
            if new_calib not in old_list:
                old_list.append(new_calib)
            self.config["ranges"] = old_list
            self.logger.debug("Neue Liste ist jetzt {}".format(self.config["ranges"]))

    def laodZeroMap(self, name=None):
        cb = self.brightness()
        if cb == -1:
            self.states["extendet"] = "Error: Brightness"
            return
        self.states["brightness"] = cb
        ll = self.config.get("ranges", None)
        if ll is None or self.__zeromap_data is None:
            return
        if len(ll) < 1:
            return
        if self.zeromap_py["isBuilding"]:
            return
        found = min(ll, key=lambda x: abs(Analyzer.getMin(x[0], x[1], cb) - cb) )
        
        if name is not None:
            found = filter(lambda x: x[2] == name, ll)
            found = list(found)
            if len(found) > 0:
                found = found[0]
            else:
                found = None
                
        if found is not None and found[2] != self.states["zmdata"]:
            f,n = self.config.getIndependendFile(name=found[2], no_watchdog=True)
            d = f["pimotion/data"]
            self.logger.debug("Lade Savedata in C zeroMap von {}".format(n))
            self.__zeromap_data.loadZeroMap(d)
            self.states["zmdata"] = found[2]
            self.states["lowest_brightness"] = found[0]
            self.states["highest_brightness"] = found[1]
            self.states["extendet"] = "ZM {} wg BR {} geladen".format(found[2], cb)
            f.stop()
        elif found is None:
            self.states["extendet"] = "Keine zmdata gefunden!"
        elif found[2] == self.states["zmdata"]:
            self.states["extendet"] = ""
        return found is not None

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
        
        if self.__frame_drop > 0:
            self.logger.warning("Framedrop")
            self.__frame_drop -= 1
            return

        not_subtracted = a
        if self.zeromap_py["enabled"] and self.__zeromap_data != None and not self.zeromap_py["isBuilding"]:
            try:
                a = self.__zeromap_data.subtractMask(a)
            except:
                self.logger.exception("Subtract failed")

        if self.config.get("hottestBlock", False):
            hottestBlock = Mods.PiCameraMotion.analyze.hotblock.hotBlock(
                a, self.rows, self.cols, self.blockMinNoise)
            try:
                self._queue.put_nowait((hottestBlock, a, not_subtracted))
            except queue.Full:
                self.logger.debug("Queue ist voll")
                self.states["still_frames"] = 0
                self.states["motion_frames"] = 0
                self.__frame_drop = 20
                try:
                    self.motion_call(False, self.states, False)
                except:pass
        elif self.config.get("MotionDedector/enabled", True):
            if self._motion is None and self.rows > 0 and self.cols > 0:
                self._motion = Mods.PiCameraMotion.analyze.motion.MotionDedector(
                    rows = self.rows,
                    cols = self.cols,
                    window = self.postsecs*self._fps,
                    area = self.config.get("MotionDedector/area", 25),
                    frames=self.frameToTriggerMotion
                )
            if self._motion is not None:
                try:
                    changed, motion = self._motion.analyse(a)
                    if changed:
                        br = self.brightness()
                        ld = self.states.get("brightness", 0) - br
                        self.states["brightness"] = br
                        if self.config.get("MotionDedector/lightDiffBlock", None) is not None and ld < self.config.get("MotionDedector/lightDiffBlock", None):
                            self.logger.info("Bewegung blockiert. Grund: Helligkeit rapide gefallen.")
                        else:
                            self.motion_call(
                                motion > 0,{
                                    "motion": 1 if  motion > 0 else 0,
                                    "val": motion,
                                    "type": "MotionDedector",
                                    "brightness": br,
                                    "brightness_change": ld
                                },
                                False
                            )
                    elif self._framecount > 1140:
                        br = self.brightness()
                        ld = self.states.get("brightness", 0) - br
                        self.states["brightness"] = br
                        self._framecount = 0
                        self.logger.debug("Neue Helligkeit: {}".format(br))
                        self.motion_data_call({
                                    "type": "brightness",
                                    "brightness": br,
                                    "brightness_change": ld
                                },
                                True
                            )

                    self.processed += 1
                    self._framecount += 1
                except:
                    self.logger.exception("MotionDedector")
                    self._motion = None
            

    def trainZeroMap(self, update=False, data=None):
        with self._analyzer_lock:
            if data == False:
                self.saveZeroMap(isUpdate=True)
                self.__zeromap_block_loader = False
                self.__zeromap_data_trainee_id = ""
                self.states["extendet"] = ""
                return
            elif data is not None:
                self.states["extendet"] = "Trainingsdaten werden verarbeitet"
                self.__zeromap_block_loader = True
                if data.get("exif_zeromap", None) is not None:
                    zm = data["exif_zeromap"]
                    if self.__zeromap_data_trainee_id != zm["zn"]:
                        self.__zeromap_data_trainee_id = zm["zn"]
                        self.saveZeroMap(isUpdate=True)
                        if  not self.laodZeroMap(zm["zn"]):
                            self.logger.warning("trainZeroMap() rm[\"zn\"] = {} nicht gefunden.".format(zm["zn"]))
                            return
                    self.__zeromap_data.trainFromDict(zm["zd"])                   
                return

            if not update or self.__zeromap_data is None:
                self.__zeromap_data = Mods.PiCameraMotion.analyze.hotblock.ZeroMap(self.rows, self.cols)
                self.logger.debug("Erstelle C Object for zeroMap...")
                self.states["lowest_brightness"] = 1000000
                self.states["highest_brightness"] = 0
                self.states["zmdata"] = None
            self.logger.info("Schalte zeroMap ein...")
            self.zeromap_py["enabled"] = True
            self.logger.info("Schalte zeroMap Baustatus um...")
            self.zeromap_py["isBuilding"] = True
            self.states["still_frames"] = 0
            self.states["extendet"] = "ZeroMap aktualisieren" if update else "ZeroMap erstellen"
    
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
        changed = self.__zeromap_data.trainZeroMap(a, True)
        still_pre_change = self.states["still_frames"]
        br = -1
        if changed:
            self.states["still_frames"] = 0
            self.states["motion_frames"] += 1
            # if self.states.get("brightness_holdoff", 0) <= 0:
            #             self.states["highest_brightness"] = br
            #     self.states["brightness_holdoff"] = 60
            # else:
            #     self.states["brightness_holdoff"] -= 1
            br = self.brightness()
            ld = self.states["brightness"] - br
            self.states["brightness"] = br
            if br > -1:
                if self.states.get("lowest_brightness", 1000000) > br:
                    self.states["lowest_brightness"] = br
                if self.states.get("highest_brightness", 0) < br:
                    if self.lightDiffBlock > -1 and self.lightDiffBlock <= ld:
                        self.logger.debug("Brightness {} changed too much! Config: {}".format(ld, self.lightDiffBlock))
                        self.states["still_frames"] += 1
                        self.states["motion_frames"] = 0
                    else:
                        self.states["motion_frames"] += 1
                        self.logger.debug("Brightness {}  OK! Config: {}".format(ld, self.lightDiffBlock))
                        self.__zeromap_data.trainZeroMap(a, False)

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
        elif self.states["still_frames"] >= self.framesToNoMotion:
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

            while True:
                with self._analyzer_lock:
                    hottestBlock, a, origa = self._queue.get()
                if not self.__thread_do_run:
                    break
                self.processed += 1
                self.states["hotest"] = [hottestBlock[0],
                                        hottestBlock[1], hottestBlock[2]]
                self.states["noise_count"] = hottestBlock[3]
                self.states["object"] = hottestBlock

                if self.zeromap_py["isBuilding"]:
                    self.__train_zero(a)

                elif self.countMinNoise > hottestBlock[3] and self.countMaxNoise > hottestBlock[3] and hottestBlock[2] < self.blockMinNoise:
                    self.states["still_frames"] += 1
                    self.states["motion_frames"] = 0
                else:
                    new_light = self.brightness()
                    ld = self.states["brightness"] - new_light
                    if ld < 0:
                        ld = ld *-1
                    if self.lightDiffBlock > -1 and self.lightDiffBlock <= ld:
                        self.logger.debug("Brightness {} changed too much! Config: {}".format(ld, self.lightDiffBlock))
                        self.states["still_frames"] += 1
                        self.states["motion_frames"] = 0
                    else:
                        self.states["motion_frames"] += 1
                        self.logger.debug("Brightness {}  OK! Config: {}".format(ld, self.lightDiffBlock))
                            
                if self.zeromap_py["isBuilding"] and self.states["still_frames"] > self.framesToNoMotion:
                    self.saveZeroMap()
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
                elif not self._calibration_running:
                    try:
                        if self.states["noise_count"] >= self.countMinNoise or self.states["hotest"][2] > self.blockMinNoise:
                            self.motion_data_call(self.states)
                    except Exception as e:
                        self.logger.exception(
                            "Motion data call Exception: {}".format(str(e)))
                    try:
                        if self.states["motion_frames"] >= self.frameToTriggerMotion and not self.__motion_triggered:
                            # Speichere Magnitude Picture
                            try:
                                if self.states["motion_frames"] >= self.frameToTriggerMotion and not self.__motion_triggered:
                                    self.pil_magnitude_save_call(a, self.__old_States)
                                    if self.zeromap_py["enabled"]:
                                        to_give = copy.deepcopy(self.states)
                                        trainData = self.__zeromap_data.trainConvertToDict(origa)
                                        to_give["exif_zeromap"] = {}
                                        to_give["exif_zeromap"]["zd"] = trainData
                                        to_give["exif_zeromap"]["zn"] = self.states.get("zmdata", "")
                                        self.pil_magnitude_save_call(a, to_give)
                                    else:
                                        self.pil_magnitude_save_call(a, self.states)
                                else:
                                    self.__old_States = copy.deepcopy(self.states)
                            except:
                                self.logger.exception("Kann magnitude nicht speichern!")
                            
                            # Motion detector
                            self.states["motion_frames"] = 0
                            self.__motion_triggered = True
                            self.logger.debug("Trigger Motion")
                            self.states["still_frames"] = 0
                            self.states["lightDiff"] = ld
                            self.motion_call(True, self.states, False)
                            try:
                                if not self.__zeromap_block_loader:
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
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def stop_queue(self, exception=None):
        self.__thread_do_run = False
        try:
            self._queue.put_nowait((None, None, None))
        except queue.Full:
            pass
        schedule.cancel_job(self._shed_task)
        self.config["zeroMap"] = self.zeromap_py
        if exception is not None:
            self.states["ext"] = str(exception)
        self.motion_call(False, self.states, False)
