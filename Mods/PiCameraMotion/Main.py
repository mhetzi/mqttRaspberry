# -*- coding: utf-8 -*-

import queue
import pathlib
import datetime as dt
import json
import Tools.PluginManager as pm
import paho.mqtt.client as mclient

from  Tools.Config import BasicConfig, PluginConfig
from Tools.ResettableTimer import ResettableTimer
import Tools.Autodiscovery as autodisc
import logging
import io
import shutil

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

import threading
import Mods.PiCameraMotion.etc as etc
import Mods.PiCameraMotion.http as httpc

import Mods.PiCameraMotion.rtsp as rtsp
import Mods.PiCameraMotion.analyzers as analyzers
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
    _rtsp_recorder = None
    _analyzer = None
    _postRecordTimer = None
    _pilQueue = None
    _pilThread = None
    _http_out = None
    _sendDebug = False

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

    def set_do_record(self, recording: bool):
        self.__logger.info(
            "Config Wert aufnehmen wird auf {} gesetzt".format(recording))
        self._config["record/enabled"] = recording
        self.__client.publish(self._do_record_topic.state,
                              payload=b'ON' if recording else b'OFF')

    def set_do_dbg(self, debug: bool):
        self.__logger.info(
            "Config Wert Dbg wird auf {} gesetzt".format(debug))
        self.__client.publish(self._do_record_topic.state,
                              payload=b'ON' if debug else b'OFF')

    def on_message(self, client, userdata, message: mclient.MQTTMessage):
        if self._do_record_topic.command == message.topic:
            if message.payload.decode('utf-8') == "ON":
                self.set_do_record(True)
            elif message.payload.decode('utf-8') == "OFF":
                self.set_do_record(False)

    def on_dbg_message(self, client, userdata, message: mclient.MQTTMessage):
        if self._do_record_topic.command == message.topic:
            if message.payload.decode('utf-8') == "ON":
                self.set_do_dbg(True)
            elif message.payload.decode('utf-8') == "OFF":
                self.set_do_dbg(False)

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
        self.__client.publish(
            self._motion_topic.ava_topic, "online", retain=True)
        self.__client.will_set(
            self._motion_topic.ava_topic, "offline", retain=True)
        # Setup MQTT debug sensor
        uid_debug = "switch.piMotion-dbg-{}-{}".format(
            self._device_id, sensorName)
        self._debug_topic = self._config.get_autodiscovery_topic(
            autodisc.Component.SWITCH,
            sensorName,
            autodisc.SensorDeviceClasses.GENERIC_SENSOR
        )
        debug_payload = self._debug_topic.get_config_payload(
            sensorName, "", unique_id=uid_debug, value_template="{{ value_json.on_dbg_message }}", json_attributes=True)
        if self._debug_topic.config is not None:
            self.__client.publish(self._debug_topic.config,
                                  payload=debug_payload, qos=0, retain=True)
        self.__client.publish(
            self._debug_topic.ava_topic, "online", retain=True)
        self.__client.will_set(
            self._debug_topic.ava_topic, "offline", retain=True)
        self.__client.subscribe(self._debug_topic.command)
        self.__client.message_callback_add(
            self._debug_topic.command, self.on_dbg_message)
        # Setup MQTT recording switch
        switchName = "{} Aufnehmen".format(sensorName)
        uid_do_record = "switch.piMotion-{}-{}".format(
            self._device_id, switchName.replace(" ", "_"))
        self._do_record_topic = self._config._main.get_autodiscovery_topic(
            autodisc.Component.SWITCH,
            switchName,
            autodisc.SensorDeviceClasses.GENERIC_SENSOR
        )
        do_record_payload = self._do_record_topic.get_config_payload(
            switchName,
            "",
            unique_id=uid_do_record
        )
        if self._do_record_topic is not None:
            self.__client.publish(
                self._do_record_topic.config, payload=do_record_payload, qos=0, retain=True)
        self.__client.publish(
            self._do_record_topic.ava_topic, "online", retain=True)
        self.__client.will_set(
            self._do_record_topic.ava_topic, "offline", retain=True)
        self.__client.subscribe(self._do_record_topic.command)
        self.__client.message_callback_add(
            self._do_record_topic.command, self.on_message)
        self.set_do_record(self._config.get("record/enabled", True))

        # Starte thread
        if not wasConnected:
            self.start()
            self._pilThread = threading.Thread(
                target=self.pil_magnitude_save, name="MagSave")
            self._pilThread.start()

        self.set_do_dbg(self._sendDebug)

    def set_pluginManager(self, p: pm.PluginManager):
        self._pluginManager = p

    def stop(self):
        self.stop_record()
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
        if self._rtsp_split is not None:
            self._rtsp_split.shutdown()
        self.__client.publish(self._motion_topic.ava_topic,
                              "offline", retain=True)

        if self._analyzer is not None:
            self._analyzer.stop_queue()

        if self._pilQueue is not None and self._pilThread is not None:
            self.__logger.info("Warte auf PIL Thread...")
            self._pilThread.join(10)
            self._pilQueue = None

    def run(self):
        import time
        time.sleep(5)
        self.__logger.debug("PiMotion.run()")
        with cam.PiCamera(clock_mode='raw', framerate=self._config.get("camera/fps", 23)) as camera:
            self._camera = camera
            # Init Kamera
            camera.resolution = (
                self._config["camera/width"], self._config["camera/height"])
            camera.video_denoise = self._config.get(
                "camera/denoise", True)
            self.__logger.debug("Kamera erstellt")

            camera.annotate_background = cam.Color('black')
            camera.annotate_text = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            with analyzers.Analyzer(camera, logger=self.__logger.getChild("Analyzer"), config=self._config) as anal:
                self.__logger.debug("Analyzer erstellt")
                anal.frameToTriggerMotion = self._config.get(
                    "motion/motion_frames", 4)
                anal.framesToNoMotion = self._config.get(
                    "motion/still_frames", 4)
                anal.blockMinNoise = self._config.get(
                    "motion/blockMinNoise", 0)
                anal.countMinNoise = self._config.get(
                    "motion/frameMinNoise", 0)
                anal.countMaxNoise = self._config.get(
                    "motion/frameMaxNoise", 0)
                anal.motion_call = lambda motion, data, mes: self.motion(
                    motion, data, mes)
                anal.motion_data_call = lambda data: self.motion_data(data)
                anal.pil_magnitude_save_call = lambda img, data: self.pil_magnitude_save_call(
                    img, data)
                anal.cal_getMjpeg_Frame = self.getMjpegFrame

                anal.zeromap_py = self._config.get("zeroMap", {"enabled": False, "isBuilding": False, "dict": None})

                self._analyzer = anal

                self._circularStream = cam.PiCameraCircularIO(
                    camera, seconds=self._config["motion/recordPre"])

                if self._config.get("rtsp/enabled", True):
                    self.__logger.debug("Erstelle CameraSplitIO")
                    rtsp_split = rtsp.CameraSplitIO(camera)
                    self._rtsp_split = rtsp_split
                    rtsp_split.logger = self.__logger
                    rtsp_split.initAndRun(self._circularStream, file=None)
                    self.__logger.info("Aktiviere RTSP...")
                    rtsp_server = rtsp.GstRtspPython(
                        self._config.get("camera/fps", 23),
                        self._config["motion/sensorName"]
                    )
                    rtsp_server.logger = self.__logger.getChild("RTSP_srv")
                    self.__logger.info("Starte RTSP...")

                    def run():
                        try:
                            rtsp_server.runServer()
                        except KeyboardInterrupt:
                            self._pluginManager.shutdown()

                    t = threading.Thread(name="rtsp_server", target=run)
                    t.start()
                    self._rtsp_server = rtsp_server

                camera.start_recording(self._circularStream, format='h264',
                                       motion_output=anal, quality=25, sps_timing=True,
                                       intra_period=self._config.get("camera/fps", 23) * 5,
                                       sei=True, inline_headers=True, bitrate=0)

                if self._config.get("http/enabled", False):
                    self.__logger.info("Aktiviere HTTP...")
                    http_out = httpc.StreamingOutput()
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
                    streamingHandle.update_settings_call = lambda s, a,b,c,d,e: self.update_settings_call(a,b,c,d,e)
                    streamingHandle.jpegUpload_call = lambda s,d: self.parseTrainingPictures(d)

                    server = httpc.StreamingServer(address, streamingHandle)
                    server.logger = self.__logger.getChild("HTTP_srv")
                    self._http_server = server

                    camera.start_recording(
                        http_out, format='mjpeg', splitter_port=2)
                    t = threading.Thread(name="http_server", target=server.run)
                    self.__logger.info("Starte HTTP...")
                    t.start()
                # Und jetzt einfach warten

                anal.disableAnalyzing = not self._config.get("motion/doAnalyze", True)

                def first_run():
                    time.sleep(2)
                    self.__logger.info(
                        "Stream wird sich normalisiert haben. Queue wird angeschlossen...")
                    anal.run_queue()
                threading.Thread(target=first_run, name="Analyzer bootstrap", daemon=True).run()
                
                while not self._doExit:
                    try:
                        camera.wait_recording(5)
                        pps = anal.processed / 5
                        anal.processed = 0
                        self.__logger.debug("Pro Sekunde verarbeitet: %d", pps)

                        if anal.disableAnalyzing:
                            camera.annotate_text = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        self.__logger.exception("Kamera Fehler")
                        exit(-1)
                anal.stop_queue()
        try:
            server.stop()
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
        self._camera = None

    def update_anotation(self, aps=0):
        if self._camera is not None:
            txt_motion = "" if self._inMotion else ""

            self._camera.annotate_text = txt_motion

            # self._camera.annotate_text = text1 + " {} {}APS {} {} {} {}".format(
            #    txt_motion, aps,
            #    self._lastState["x"], self._lastState["y"], self._lastState["val"], self._lastState["c"]
            # )

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
        if self._rtsp_recorder is not None:
            self._rtsp_recorder.shutdown()
            self._rtsp_recorder = None
            self._rtsp_split._restore_append()
        self._postRecordTimer = None

    def motion(self, motion: bool, data: dict, wasMeassureing: bool):
        if wasMeassureing:
            self._config["motion/blockMinNoise"] = self._analyzer.blockMaxNoise
            self._config["motion/frameMinNoise"] = self._analyzer.countMinNoise
            self._config["zeroMap"] = self._analyzer.zeromap_py
            self._config.save()
        if motion:
            self.__logger.info("Motion")
            if self._config.get("record/enabled", True):
                path = self._config.get("record/path", "~/Videos")
                if not path.endswith("/"):
                    path += "/"
                path = "{}/aufnahmen/{}.h264".format(
                    path, dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                if self._postRecordTimer is None and self._rtsp_recorder is None:
                    self._rtsp_recorder = self._rtsp_split.recordTo(path=path)
                elif self._postRecordTimer is not None:
                    self._postRecordTimer.cancel()
                    self._postRecordTimer = None
                    self.__logger.debug("Aufname timer wird zurückgesetzt")
        else:
            self.__logger.info("No Motion")
            if self._postRecordTimer is not None:
                self._postRecordTimer.cancel()
                self._postRecordTimer = None
                self.__logger.debug("Aufname timer wird zurückgesetzt")
            self._postRecordTimer = ResettableTimer(
                interval=self._config.get("motion/recordPost", 1),
                function=self.stop_record,
                autorun=True
            )
            self.__logger.debug("Aufnahme wird in {} Sekunden beendet.".format(
                self._config.get("motion/recordPost", 1)))

        self._inMotion = motion
        self.motion_data(data=data, changed=True)

    def motion_data(self, data: dict, changed=False):
        # x y val count
        self._lastState = {"motion": 1 if self._inMotion else 0, "x": data["hotest"][0],
                           "y": data["hotest"][1], "val": data["hotest"][2], "c": data["noise_count"], "dbg_on": self._sendDebug,
                           "ext": data["extendet"], "brightness": data["brightness"]}
        self._jsonOutput.write(self._lastState)
        self.update_anotation()
        if self._analyzer is not None and not self._analyzer._calibration_running:
            self.sendStates(changed=changed)

    def sendStates(self, changed=None):
        if changed is None:
            self.__client.publish(self._motion_topic.state, json.dumps(self._lastState))
            self.__client.publish(self._debug_topic.state, json.dumps(self._lastState))
        elif changed:
            self.__client.publish(self._motion_topic.state, json.dumps(self._lastState))
        elif self._sendDebug:
            self.__client.publish(self._debug_topic.state, json.dumps(self._lastState))

    def pil_magnitude_save_call(self, d, data: dict):
        if self._pilQueue is not None:
            try:
                self._pilQueue.put_nowait((d, data))
            except queue.Full:
                pass

    def getMjpegFrame(self):
        frame = None
        with self._http_out.condition:
            frame = self._http_out.frame
        return frame


    def pil_magnitude_save(self):
        while True:
            try:
                a, data = self._pilQueue.get(timeout=5)
            except queue.Empty:
                if self._doExit:
                    self.__logger.warning("PIL Magnitude Save Thread wird beendet")
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
                draw.text((0,60), dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), fill=(255, 255, 0, 155), font=self._image_font)

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

                    bio.seek(0)
                    shutil.copyfileobj(bio, file)

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
                self._camera.shutter_speed,
                self._camera.exposure_speed,
                self._camera.exposure_mode,
                cv[0], cv[1],
                self._camera.iso
            )
        return html

    def update_settings_call(self, countMaxNoise, countMinNoise, blockMinNoise, frameToTriggerMotion, framesToNoMotion):
        self._analyzer.countMaxNoise       = countMaxNoise
        self._analyzercountMinNoise        = countMinNoise
        self._analyzerblockMinNoise        = blockMinNoise
        self._analyzerframeToTriggerMotion = frameToTriggerMotion
        self._analyzerframesToNoMotion     = framesToNoMotion

        self._config["motion/motion_frames"] = frameToTriggerMotion
        self._config["motion/still_frames" ] = framesToNoMotion
        self._config["motion/blockMinNoise"] = blockMinNoise
        self._config["motion/frameMinNoise"] = countMinNoise
        self._config["motion/frameMaxNoise"] = countMaxNoise
        self._config.save()
