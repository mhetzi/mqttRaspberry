# -*- coding: utf-8 -*-

import queue
import pathlib
import datetime as dt
import json
import Tools.PluginManager as pm
import paho.mqtt.client as mclient
import schedule

from  Tools.Config import BasicConfig, PluginConfig
from Tools.ResettableTimer import ResettableTimer
import Tools.Autodiscovery as autodisc
import logging
import io
import shutil
from math import nan, isnan

try:
    import picamera as cam
    import picamera.array as cama
except ImportError:
    import Mods.referenz.picamera.picamera as cam
    import Mods.referenz.picamera.picamera.array as cama

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('pillow', throw=ie, ask=True)
    except err.RestartError:
        from PIL import Image, ImageDraw, ImageFont
try:
    import numpy as np
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('numpy', throw=ie, ask=True)
    except err.RestartError:
        import numpy

try:
    import piexif
    import piexif.helper
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('piexif', throw=ie, ask=True)
    except err.RestartError:
        import piexif
        import piexif.helper

try:
    import scipy
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('scipy', throw=ie, ask=True)
    except err.RestartError:
        import scipy

import threading
import Mods.PiCameraMotion.etc as etc
import Mods.PiCameraMotion.http as httpc

import Mods.PiCameraMotion.rtsp as rtsp
import Mods.PiCameraMotion.analyzers as analyzers

from Mods.PiCameraMotion.gstreamer.SplitStream import CameraSplitter
from Mods.PiCameraMotion.gstreamer.RTSPServer import GstServer, PiCameraMediaFactory
from Mods.PiCameraMotion.gstreamer.PreRecordBuffer import PreRecordBuffer
try:
    import pyximport
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('cython', throw=ie, ask=True)
    except err.RestartError:
        import pyximport

pyximport.install()

try:
    import picamera
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('picamera[array]', throw=ie, ask=True)
    except err.RestartError:
        import picamera

class PiMotionMain(threading.Thread):

    _motionStream = etc.NullOutput()
    _webStream = etc.NullOutput()
    _circularStream = None
    _inMotion = None
    _pluginManager = None
    _rtsp_server = None
    _http_server = None
    _rtsp_split = None
    _jsonOutput = None
    _motion_topic = None
    _debug_topic = None
    _do_record_topic = None
    _lastState = {"motion": 0, "x": 0, "y": 0, "val": 0, "c": 0}
    _analyzer = None
    _postRecordTimer = None
    _pilQueue = None
    _pilThread = None
    _http_out = None
    _sendDebug = False
    _splitStream = None
    _record_factory = None
    _snapper = None
    _annotation_updater = None
    _err_topics = None
    _brightness_topic = None
    __last_brightness = nan

    bitrate = 17000000
    _area = 25 # number of connected MV blocks (each 16x16 pixels) to count as a moving object
    _frames = 4 # number of frames which must contain movement to trigger

    def __init__(self, client: mclient.Client, opts: BasicConfig, logger: logging.Logger, device_id: str):
        threading.Thread.__init__(self)
        self.__client = client
        self.__logger = logger.getChild("PiMotion")
        self._config = PluginConfig(opts, "PiMotion")
        self._device_id = device_id

        self.__logger.debug("PiMotion.__init__()")

        self.setName("PiCamera")
        self.__logger.debug("PiMotion.register()")
        self._doExit = False
        self._camera = None

        path = self._config.get("record/path", "~/Videos")
        if not path.endswith("/"):
            path += "/"
        path = "{}/aufnahmen/".format(path)
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)

        path = self._config.get("record/path", "~/Videos")
        if not path.endswith("/"):
            path += "/"
        path = "{}/magnitude/".format(path)
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)
        self._image_font = ImageFont.truetype(
            font=self._config.get(
                "font", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            size=9,
            encoding="unic"
        )

        self._pilQueue = queue.Queue(5)
        self._splitStream = None  
        self._err_topics = None
        self.was_errored = True

    def set_do_record(self, recording: bool):
        self.__logger.info(
            "Config Wert aufnehmen wird auf {} gesetzt".format(recording))
        self._config["record/enabled"] = recording

    def register(self, wasConnected=False):
        # Setup MQTT motion binary_sensor
        sensorName = self._config["motion/sensorName"]
        uid_motion = "binary_sensor.piMotion-{}-{}".format(
            self._device_id, sensorName)
        self._motion_topic = self._config._main.get_autodiscovery_topic(
            autodisc.Component.BINARY_SENROR,
            sensorName,
            autodisc.BinarySensorDeviceClasses.MOTION
        )
        motion_payload = self._motion_topic.get_config_payload(
            sensorName, "", unique_id=uid_motion, value_template="{{ value_json.motion }}", json_attributes=True)
        if self._motion_topic.config is not None:
            self.__client.publish(self._motion_topic.config,
                                  payload=motion_payload, qos=0, retain=True)

        self.set_do_record(self._config.get("record/enabled", True))
        
        errName = "{} Kamera Fehler".format(sensorName)
        self._err_topics = self._config.get_autodiscovery_topic(
            autodisc.Component.BINARY_SENROR,
            errName,
            autodisc.BinarySensorDeviceClasses.PROBLEM
        )
        self._err_topics.register(
            self.__client,
            errName,
            "",
            value_template="{{value_json.err}}",
            json_attributes=True,
            unique_id="cam.main.error.{}".format(self._config._main.get_client_config().id)
        )
        self.__client.publish(
            self._err_topics.state,
            json.dumps({
                "err": 1,
                "Grund": "Starting..."
            })
        )
        
        self._brightness_topic = self._config.get_autodiscovery_topic(
            autodisc.Component.SENSOR,
            "Bildhelligkeit",
            autodisc.SensorDeviceClasses.ILLUMINANCE
        )
        
        self._brightness_topic.register(
            self.__client,
            "Bildhelligkeit",
            "pxLux",
            value_template="{{value_json.brightness}}",
            json_attributes=True,
            unique_id="cam.main.bright.{}".format(self._config._main.get_client_config().id)
        )
        self.was_errored = True

        # Starte thread
        if not wasConnected:
            self.start()
            self._pilThread = threading.Thread(
                target=self.pil_magnitude_save, name="MagSave")
            self._pilThread.start()

    def set_pluginManager(self, p: pm.PluginManager):
        self._pluginManager = p

    def stop(self):
        self.stop_record()
        if self._record_factory:
            self._record_factory.destroy()
        self._doExit = True
        if self._pilQueue is not None and self._pilThread is not None:
            self.__logger.info("Stoppe PIL queue...")
            try:
                self._pilQueue.put((None, None), block=False)
            except queue.Full:
                pass
        if self._rtsp_server is not None:
            self._rtsp_server.stopServer()
        if self._http_server is not None:
            self._http_server.stop()
        self.__client.publish(self._motion_topic.ava_topic,
                              "offline", retain=True)

        if self._analyzer is not None:
            self._analyzer.stop_queue()

        if self._pilQueue is not None and self._pilThread is not None:
            self.__logger.info("Warte auf PIL Thread...")
            self._pilThread.join(10)
            self._pilQueue = None
        if self._http_out is not None:
            self._http_out.shutdown()

    def setupAnalyzer(self, camera: cam.PiCamera):
        anal = analyzers.Analyzer(
            camera,
            logger=self.__logger.getChild("Analyzer"),
            config=self._config,
            fps=self._config["camera/fps"],
            postSecs=self._config.get("motion/recordPost", 1)
        )
        # SET SETTINGS
        anal.frameToTriggerMotion = self._config.get("motion/motion_frames", 4)
        anal.framesToNoMotion = self._config.get("motion/still_frames", 4)
        anal.blockMinNoise = self._config.get("motion/blockMinNoise", 0)
        anal.countMinNoise = self._config.get("motion/frameMinNoise", 0)
        anal.countMaxNoise = self._config.get("motion/frameMaxNoise", 0)
        anal.lightDiffBlock = self._config.get("motion/lightDiffBlock", -1)
        anal.zeromap_py = self._config.get("zeroMap", {"enabled": False, "isBuilding": False, "dict": None})
        anal.disableAnalyzing = not self._config.get("motion/doAnalyze", True)
        # SET CALLBACKS
        anal.motion_call = lambda motion, data, mes: self.motion(motion, data, mes)
        anal.motion_data_call = lambda data, changed: self.motion_data(data, changed)
        anal.pil_magnitude_save_call = lambda img, data: self.pil_magnitude_save_call(img, data)
        anal.cal_getMjpeg_Frame = self.getMjpegFrame
        self._analyzer = anal

    def setupRTSP(self):
        factory = PiCameraMediaFactory(
            fps=self._config["camera/fps"],
            CamName=self._config["motion/sensorName"],
            log=self.__logger.getChild("RTSP_Factory"),
            splitter=self._splitStream #,wh=(self._config["camera/width"], self._config["camera/height"])
        )
        
        server = GstServer(factory=factory, logger=self.__logger)
        server.runServer()
        self._rtsp_server = server

    def setupRecordFactory(self) -> PreRecordBuffer:
        factory = PreRecordBuffer(
            secs_pre=self._config["motion/recordPre"],
            fps=self._config["camera/fps"],
            camName=self._config["motion/sensorName"],
            logger=self.__logger, 
            splitter=self._splitStream,
            path=pathlib.Path(self._config["record/path"]),
            wh=(self._config["camera/width"], self._config["camera/height"])
        )
        factory.start()
        self._record_factory = factory
        return factory

    def setupHttpServer(self):
        self.__logger.info("Aktiviere HTTP...")
        http_out = httpc.StreamingOutput(self.__logger)
        self._http_out = http_out

        self._jsonOutput = httpc.StreamingJsonOutput()
        address = (
            self._config.get("http/addr", "0.0.0.0"),
            self._config.get("http/port", 8083)
        )   
        streamingHandle = httpc.makeStreamingHandler(http_out, self._jsonOutput)
        streamingHandle.logger = self.__logger.getChild("HTTPHandler")
        streamingHandle.meassure_call = lambda s,i: self.meassure_call(i)
        streamingHandle.fill_setting_html = lambda s, html: self.fill_settings_html(html)
        streamingHandle.update_settings_call = lambda s, a,b,c,d,e,f: self.update_settings_call(a,b,c,d,e,f)
        streamingHandle.jpegUpload_call = lambda s,d: self.parseTrainingPictures(d)
        streamingHandle.set_anal_onhold = lambda s,x: self.set_anal_onhold(x)
        streamingHandle.save_snapshot = lambda s: self.takeSnapshot()

        server = httpc.StreamingServer(address, streamingHandle)
        server.logger = self.__logger.getChild("HTTP_srv")
        self._http_server = server

    def run(self):
        import time
        time.sleep(5)
        self.__logger.debug("PiMotion.run()")
        with cam.PiCamera(clock_mode='raw', framerate=self._config.get("camera/fps", 23)) as camera:
            self._camera = camera
            self._splitStream = CameraSplitter(camera=camera, log=self.__logger)  
            # Init Kamera
            camera.resolution = (self._config["camera/width"], self._config["camera/height"])
            camera.video_denoise = self._config.get("camera/denoise", True)
            self.__logger.debug("Kamera erstellt")

            camera.annotate_background = cam.Color('black')
            camera.annotate_text = dt.datetime.now().strftime('Gestartet am %d.%m.%Y um %H:%M:%S')

            self.setupAnalyzer(camera)
            
            with  self._analyzer:
                self.__logger.debug("Analyzer erstellt")
                
                if self._config.get("rtsp/enabled", True):
                    self.setupRTSP()

                self.setupRecordFactory()    

                self._splitStream.splitter_port = 1
                camera.start_recording(
                    self._splitStream,
                    format='h264', profile='high', level='4.1',
                    splitter_port=1,
                    motion_output=self._analyzer, quality=25, sps_timing=True,
                    intra_period=int(self._config.get("camera/fps", 23) / 1.5),
                    sei=True, inline_headers=True, bitrate=self.bitrate
                )

                if self._config.get("http/enabled", False):
                    self.setupHttpServer()

                    camera.start_recording(
                        self._http_out, format='mjpeg', splitter_port=2)
                    t = threading.Thread(name="http_server", target=self._http_server.run)
                    self.__logger.info("Starte HTTP...")
                    t.start()
                # Und jetzt einfach warten

                def first_run():
                    time.sleep(2)
                    self.__logger.info(
                        "Stream wird sich normalisiert haben. Queue wird angeschlossen...")
                    self._analyzer.run_queue()
                    self.update_anotation()
                threading.Thread(target=first_run, name="Analyzer bootstrap", daemon=True).start()
                
                exception_raised = False
                sleep_seconds = 2
                while not self._doExit:
                    try:
                        camera.wait_recording(sleep_seconds, splitter_port=1)
                        if self._analyzer.disableAnalyzing:
                            pps = self._splitStream.written / sleep_seconds
                            self._splitStream.written = 0
                        else:
                            pps = self._analyzer.processed / sleep_seconds
                            self._analyzer.processed = 0
                        fps = self._config.get("camera/fps", 23)
                        if int(fps) != int(pps):
                            self.__logger.warning("Pro Sekunde verarbeitet: %d, sollte aber %d sein", pps, fps)

                        if pps == 0 and not self.was_errored:
                            self.was_errored = True
                            self.__client.publish(
                                self._err_topics.state,
                                json.dumps({
                                    "err": 1,
                                    "Grund": "FPS ist 0"
                                })
                            )
                            import sys, traceback
                            with open("/tmp/piMotion_last_traces", "w") as f:
                                for thread_id, frame in sys._current_frames().items():
                                    print('\n--- Stack for thread {t} ---'.format(t=thread_id), file=f)
                                    traceback.print_stack(frame, file=f)

                        elif self.was_errored:
                            self.__client.publish(
                                self._err_topics.state,
                                json.dumps({
                                    "err": 0,
                                    "Grund": "Fehler verschwunden"
                                })
                            )
                            self.was_errored = False
                        self.sendBrightness()
                    except Exception as e:
                        self.__logger.exception("Kamera Fehler")
                        self._doExit = True
                        exception_raised = True
                        self._analyzer.stop_queue(e)

                if not exception_raised:
                    self._analyzer.stop_queue()
        try:
            self._http_server.stop()
        except:
            pass
        try:
            self._rtsp_server.stopServer()
        except:
            pass
        try:
            camera.stop_recording(splitter_port=2)
        except:
            pass
        try:
            camera.stop_recording()
        except:
            pass
        try:
            self._http_out.shutdown()
        except: pass
        self._camera = None

    def update_anotation(self, aps=0):
        self._annotation_updater = None
        if self._camera is not None:
            txt_motion = dt.datetime.now().strftime('%d.%m.%Y %H:%M:%S REC') if self._inMotion else dt.datetime.now().strftime('%d.%m.%Y %H:%M:%S STILL')

            self._camera.annotate_text = txt_motion
            self._annotation_updater = threading.Timer(
                interval=1, function=self.update_anotation
            )
            self._annotation_updater.start()

            #self._camera.annotate_text = text1 + " {} {}APS {} {} {} {}".format(
            #   txt_motion, aps,
            #   self._lastState["x"], self._lastState["y"], self._lastState["val"], self._lastState["c"]
            #)

    def meassure_call(self, i):
        if i == 0:
            self.meassure_minimal_blocknoise()
        elif i == 1:
            self._analyzer.trainZeroMap()
        elif i == 2:
            self._analyzer.trainZeroMap(True)
                        

    def meassure_minimal_blocknoise(self):
        self.__logger.info("Starte neue Kalibrierung...")
        self._analyzer.states["still_frames"] = 0
        self._analyzer._calibration_running = True
        self._analyzer.framesToNoMotion *= 15

    def stop_record(self):
        self._postRecordTimer = None
        self._record_factory.stop_recording()
        try:
            self.motion(False, self._lastState, False, True)
        except KeyError:
            self.__logger.exception("Sending no motion failed!")

    def do_record(self, record: bool, stopInsta=False):
        if record:
            if self._config.get("record/enabled", True):
                path = self._config.get("record/path", "~/Videos")
                if not path.endswith("/"):
                    path += "/"
                path = "{}/aufnahmen/{}.h264".format(
                    path, dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                if self._postRecordTimer is None:
                    self._record_factory.record()
                    self._postRecordTimer = ResettableTimer(
                        interval=self._config.get("motion/recordPost", 1),
                        function=self.stop_record,
                        autorun=False
                    )

                    if self._config.get("motion/takeSnapshot", False):
                        self._snapper = threading.Timer(
                            interval=self._config.get("motion/takeSnapshotSeconds", 2),
                            function=self.takeSnapshot
                        )
                        self._snapper.setName("PiMotionSnapshot")
                        self._snapper.start()
                elif self._postRecordTimer is not None:
                    self._postRecordTimer.cancel()
                    self.__logger.debug("Aufnahme timer wird zurückgesetzt")
        else:
            self.__logger.info("No Motion")
            if self._postRecordTimer is not None:
                if stopInsta:
                    self._postRecordTimer._interval = 1
                    self._postRecordTimer.reset()
                self._postRecordTimer.reset()
            
                self.__logger.debug("Aufnahme wird in {} Sekunden beendet.".format(
                    self._config.get("motion/recordPost", 1)))
            else:
                self.__logger.info("Kein Timer vorhanden. Stoppe sofort")
                self.stop_record()

    def takeSnapshot(self):
        if self._snapper is not None:
            self._snapper.cancel()
            self._snapper = None
        path = self._config.get("record/path", "~/Videos")
        if not path.endswith("/"):
            path += "/"
        path = "{}/aufnahmen/{}.jpeg".format(
            path, dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self._camera.capture(path, "jpeg", thumbnail=(64, 48, 35))


    def motion(self, motion: bool, data: dict, wasMeassureing: bool, delayed=False):
        if wasMeassureing:
            self._config["motion/blockMinNoise"] = self._analyzer.blockMaxNoise
            self._config["motion/frameMinNoise"] = self._analyzer.countMinNoise
            self._config["zeroMap"] = self._analyzer.zeromap_py
            self._config.save()

        if not delayed:
            self.do_record(motion)

        if not motion and not delayed:
            #delay the stop motion
            self._lastState = data
            return

        last = self._inMotion
        self._inMotion = motion
        
        self.motion_data(data=data, changed=last is not motion)
        #self.set_do_record(motion)

    def motion_data(self, data: dict, changed=False):
        # x y val count
        if data["type"] == "MotionDedector":
            self._lastState = {
                "motion": data["motion"], "val": data["val"],
                "type": data["type"],
                "brightness": data["brightness"],
                "lightDiff": data["brightness_change"]
            }
        elif data["type"] == "hotblock":
            self._lastState = {
                "motion": 1 if self._inMotion else 0,
                "x": data["hotest"][0], "y": data["hotest"][1],
                "val": data["hotest"][2], "c": data["noise_count"],
                "dbg_on": self._sendDebug, "ext": data["extendet"],
                "brightness": data["brightness"], "lightDiff": data["brightness_change"],
                "type": "hotBlock"
            }
        elif data["type"] == "brightness":
            self._lastState["brightness"] = data["brightness"]
            self._lastState["lightDiff"]  = data["brightness_change"]
            self.sendBrightness()
        self._jsonOutput.write(self._lastState)
        if self._analyzer is not None and not self._analyzer._calibration_running:
            self.sendStates(changed=changed)
        #self.update_anotation()

    def sendBrightness(self):
        if self.__last_brightness != self._lastState.get("brightness", nan) and not isnan(self._lastState.get("brightness", nan)):
            self.__last_brightness = self._lastState.get("brightness", nan)

            self.__client.publish(
                self._brightness_topic.state,
                json.dumps({
                    "brightness": self._lastState.get("brightness", nan),
                    "diff": self._lastState.get("lightDiff", 0)
                })
            )

    def sendStates(self, changed=None):
        if changed is None:
            self.__client.publish(self._motion_topic.state, json.dumps(self._lastState))
            self.__client.publish(self._debug_topic.state, json.dumps(self._lastState))
            self.sendBrightness()
        elif changed:
            self.__client.publish(self._motion_topic.state, json.dumps(self._lastState))
            self.sendBrightness()
        elif self._sendDebug:
            self.__client.publish(self._debug_topic.state, json.dumps(self._lastState))

    def pil_magnitude_save_call(self, d, data: dict):
        if self._pilQueue is not None:
            try:
                self._pilQueue.put_nowait((d, data))
            except queue.Full:
                pass

    def getMjpegFrame(self, block=True, timeout=-1):
        try:
            if block:
                with self._http_out.condition:
                    self._http_out.condition.wait()
                    return self._http_out.frame
            return self._http_out.frame
        except AttributeError:
            return None

    def pil_magnitude_save(self):
        while True:
            try:
                a, data = self._pilQueue.get(timeout=5)
            except queue.Empty:
                if self._doExit:
                    self.__logger.warning("PIL Magnitude Save Thread wird beendet")
                    return
                continue
            if self._doExit or a is None and data is None:
                self.__logger.warning("PIL Magnitude Save Thread wird beendet")
                return
            frame = self.getMjpegFrame()
            background = None
            try:
                if frame is not None:
                    background = Image.open(io.BytesIO(frame))
                else:
                    self.__logger.warning("Snapshot is None")
            except IOError:
                self.__logger.warning("Snapshot IOError")
            d = np.sqrt(
                np.square(a['x'].astype(np.float)) +
                np.square(a['y'].astype(np.float))
            ).clip(0, 255).astype(np.uint8)
            Bimg = Image.fromarray(d)
            img = Bimg.convert(mode="RGB", dither=Image.FLOYDSTEINBERG)
            #self.__logger.debug(data)
            if data is not None:
                ig = ImageDraw.Draw(img)
                ig.point(
                    [(data["object"][4]["col"], data["object"][4]["row"])],
                    fill=(255, 0, 0, 200)
                )
            path = pathlib.Path(self._config.get("record/path", "~/Videos"))
            path = path.joinpath(
                "magnitude",
                "{}.jpeg".format(dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            path = path.expanduser().absolute()
            self.__logger.debug('Writing %s' % path)
            if background is not None:
                self.__logger.debug("Habe Snapshot. Vermische Bilder...")
                img = img.resize( (self._config["camera/width"], self._config["camera/height"]) )
                foreground = img.convert("RGBA")
                background = background.convert("RGBA")
                img = Image.blend(background, foreground, 0.5)
            
            exif_bytes = None
            if data is not None:
                draw = ImageDraw.Draw(img)
                draw.text((0, 0), "X: {} Y: {} VAL: {} C: {}".format(data["hotest"][0], data["hotest"][1], data["hotest"][2], data["noise_count"]),
                        fill=(255, 255, 0, 155), font=self._image_font)
                draw.text((0, 20), "R: {} C: {}".format(data["object"][4]["row"], data["object"][4]["col"]),
                        fill=(255, 255, 0, 155), font=self._image_font)
                draw.text((0, 40), "B: {} Zdata: {}".format(data.get("brightness", -1), data.get("zmdata", "KEINE")), fill=(255, 255, 0, 155), font=self._image_font)
                draw.text((0,60), "BDiff: {}".format(data["lightDiff"]), fill=(255, 255, 0, 155), font=self._image_font)
                draw.text((0,80), dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), fill=(255, 255, 0, 155), font=self._image_font)

            with path.open(mode="wb") as file:
                if data is not None:
                    cimg = img.convert('RGB')
                    bio = io.BytesIO()
                    cimg.save(bio, "jpeg")

                    encoded = data #### OK Daten sind zu groß für exif villeicht anhängen?
                    extendet_data = {}
                    try:
                        extendet_data = data.get("exif_zeromap", None)
                        if extendet_data is not None:
                            del data["exif_zeromap"]
                            data["extendet_data_appendet"] = True
                        encoded = json.dumps(data)
                        user_comment = piexif.helper.UserComment.dump(encoded, encoding="unicode")

                        bio.seek(0)
                        exif_dict = piexif.load(bio.read())
                        exif_dict["Exif"][piexif.ExifIFD.UserComment] = user_comment
                        exif_bytes = piexif.dump(exif_dict)
                    except:
                        self.__logger.exception("exif_json failed")

                    if exif_bytes is not None:
                        bio = io.BytesIO()
                        cimg.save(bio, "jpeg", exif=exif_bytes)
                    if extendet_data is not None and len(extendet_data.keys()) > 0:
                        bio.write(b"=======EXTENDET_DATA=======") 
                        js_Data = json.dumps(extendet_data)
                        bio.write(js_Data.encode("utf-8"))

                    bio.flush()
                    bio.seek(0)
                    shutil.copyfileobj(bio, file)
                    file.flush()
                    file.close()

    def getExtenetData(self, data: io.BytesIO):
        data.seek(0)
        buf = data.read()
        buf = buf.split(b"=======EXTENDET_DATA=======")
        if len(buf) > 1:
            js = json.loads(buf[1])
            return js
        return {}


    def parseTrainingPictures(self, data: io.BytesIO):
        if data is None:
            self._analyzer.trainZeroMap(data=False)
            return
        try:
            data.seek(0)
            exif_dict = piexif.load(data.read())
            ucb = exif_dict["Exif"][piexif.ExifIFD.UserComment]
            ucr = piexif.helper.UserComment.load(ucb)
            ucj = json.loads(ucr)
            if ucj.get("extendet_data_appendet", False):
                ucj["exif_zeromap"] = self.getExtenetData(data)
                self._analyzer.trainZeroMap(data=ucj)
        except:
            self.__logger.exception("parseTrainingPictures()")


    def fill_settings_html(self, html: str):
        cv = self._camera.color_effects
        if cv is None:
            cv = (-1,-1)
        html = html.format(
                self._analyzer.countMaxNoise,
                self._analyzer.countMinNoise,
                self._analyzer.blockMinNoise,
                self._analyzer.frameToTriggerMotion,
                self._analyzer.framesToNoMotion,
                self._analyzer.lightDiffBlock,
                self._camera.shutter_speed,
                self._camera.exposure_speed,
                self._camera.exposure_mode,
                cv[0], cv[1],
                self._camera.iso
            )
        return html

    def update_settings_call(self, countMaxNoise, countMinNoise, blockMinNoise, frameToTriggerMotion, framesToNoMotion, lightDiff):
        self.__logger.debug("HTTP Einstellungen werden gespeichert...")
        self._analyzer.countMaxNoise       = countMaxNoise
        self._analyzer.countMinNoise        = countMinNoise
        self._analyzer.blockMinNoise        = blockMinNoise
        self._analyzer.frameToTriggerMotion = frameToTriggerMotion
        self._analyzer.framesToNoMotion     = framesToNoMotion
        self._analyzer.lightDiffBlock      = lightDiff


        self._config["motion/motion_frames"] = frameToTriggerMotion
        self._config["motion/still_frames" ] = framesToNoMotion
        self._config["motion/blockMinNoise"] = blockMinNoise
        self._config["motion/frameMinNoise"] = countMinNoise
        self._config["motion/frameMaxNoise"] = countMaxNoise
        self._config["motion/lightDiffBlock"] = lightDiff
        self._config.save()

    def set_anal_onhold(self, on_hold=None) -> bool:
        if on_hold is not None:
            self._analyzer._on_hold = on_hold
        return self._analyzer._on_hold
