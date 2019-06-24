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
import Mods.PiCameraMotion.rtsp as rtsp
import Tools.PluginManager as pm
import json
import datetime as dt

class PiMotionMain(threading.Thread):

    _motionStream   = etc.NullOutput( )
    _webStream      = etc.NullOutput( )
    _circularStream = None
    _inMotion       = None
    _pluginManager  = None
    _rtsp_server    = None
    _http_server    = None
    _rtsp_split     = None
    _jsonOutput     = None
    topic           = None
    _lastState      = { "motion": 0, "x": 0, "y": 0, "val": 0, "c": 0 }
    _rtsp_recorder  = None
    _analyzer       = None
    _postRecordTimer = None

    def __init__(self, client: mclient.Client, opts: conf.BasicConfig, logger: logging.Logger, device_id: str):
        threading.Thread.__init__(self)
        self.__client = client
        self.__logger = logger.getChild("PiMotion")
        self._config = opts
        self._device_id = device_id

        self.__logger.debug("PiMotion.__init__()")

        self.setName("PiCamera")
        self.__logger.debug("PiMotion.register()")
        self._doExit = False
        self._camera = None

    def register(self):
        # Setup MQTT zeug
        sensorName = self._config["PiMotion/motion/sensorName"]
        uid = "binary_sensor.piMotion-{}-{}".format(self._device_id, sensorName)
        self.topic = self._config.get_autodiscovery_topic(conf.autodisc.Component.BINARY_SENROR, sensorName, conf.autodisc.BinarySensorDeviceClasses.MOTION)
        payload = self.topic.get_config_payload(sensorName, "", unique_id=uid, value_template="{{ value_json.motion }}", json_attributes=True)
        if (self.topic.config is not None):
            self.__client.publish(self.topic.config, payload=payload, qos=0, retain=True)
        
        self.__client.publish(self.topic.ava_topic, "online", retain=True)
        self.__client.will_set(self.topic.ava_topic, "offline", retain=True)
        # Starte thread
        self.start()

    def set_pluginManager(self, p: pm.PluginManager):
        self._pluginManager = p

    def stop(self):
        self._doExit = True
        if self._rtsp_server is not None:
            self._rtsp_server.stopServer()
        if self._http_server is not None:
            self._http_server.stop()
        if self._rtsp_split is not None:
            self._rtsp_split.shutdown()
        if self._analyzer is not None:
            self._analyzer.stop_queue()
        self.stop_record()
        self.__client.publish(self.topic.ava_topic, "offline", retain=True)
        

    def run(self):
        self.__logger.debug("PiMotion.run()")
        with cam.PiCamera(clock_mode='raw', framerate=self._config.get("PiMotion/camera/fps", 23)) as camera:
            self._camera = camera
            # Init Kamera
            camera.resolution = (self._config["PiMotion/camera/width"], self._config["PiMotion/camera/height"])
            camera.video_denoise = self._config.get("PiMotion/camera/denoise", True)
            self.__logger.debug("Kamera erstellt")

            camera.annotate_background = cam.Color('black')
            camera.annotate_text = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            with analyzers.Analyzer(camera, logger=self.__logger.getChild("Analyzer")) as anal:
                self.__logger.debug("Analyzer erstellt")
                anal.frameToTriggerMotion = self._config.get("PiMotion/motion/motion_frames", 4)
                anal.framesToNoMotion = self._config.get("PiMotion/motion/still_frames", 4)
                anal.blockMaxNoise = self._config.get("PiMotion/motion/blockMinNoise", 0)
                anal.countMinNoise = self._config.get("PiMotion/motion/frameMinNoise", 0)
                anal.motion_call = lambda motion, data, mes: self.motion(motion, data, mes)
                anal.motion_data_call = lambda data: self.motion_data(data)
                self._analyzer = anal

                self._circularStream = cam.PiCameraCircularIO(camera, seconds=self._config["PiMotion/motion/recordPre"])

                if self._config.get("PiMotion/rtsp/enabled", True):
                    self.__logger.debug("Erstelle CameraSplitIO")
                    rtsp_split = rtsp.CameraSplitIO(camera)
                    self._rtsp_split = rtsp_split
                    rtsp_split.logger = self.__logger
                    rtsp_split.initAndRun(self._circularStream, file=None)
                    self.__logger.info("Aktiviere RTSP...")
                    rtsp_server = rtsp.GstRtspPython(
                        self._config.get("PiMotion/camera/fps", 23),
                        self._config["PiMotion/motion/sensorName"]
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
                
                camera.start_recording(self._circularStream, format='h264', motion_output=anal, quality=25, sps_timing=True, intra_period=10)

                if self._config.get("PiMotion/http/enabled", False):
                    self.__logger.info("Aktiviere HTTP...")
                    http_out = httpc.StreamingOutput()
                    pic_out = httpc.StreamingPictureOutput()
                    def capture_pic():
                        self.__logger.info("Snapshot [Threaded] wird angefertigt...")
                        camera.capture(pic_out, use_video_port=True, format="jpeg")
                    def spawn_capture_thread():
                        self.__logger.info("Erstelle thread für capture snapshot...")
                        t = threading.Thread(target=capture_pic)
                        t.setName("capture_snapshot")
                        t.setDaemon(False)
                        t.start()
                    pic_out.talkback = spawn_capture_thread
                    self._jsonOutput = httpc.StreamingJsonOutput()
                    address = (
                        self._config.get("PiMotion/http/addr","0.0.0.0"),
                        self._config.get("PiMotion/http/port",8083)
                    )
                    streamingHandle = httpc.makeStreamingHandler(http_out, self._jsonOutput, pic_out)
                    server = httpc.StreamingServer(address, streamingHandle)
                    streamingHandle.meassure_call = lambda s: self.meassure_minimal_blocknoise()
                    camera.start_recording(http_out, format='mjpeg', splitter_port=2)
                    server.logger = self.__logger.getChild("HTTP_srv")
                    t = threading.Thread(name="http_server", target=server.run)
                    self.__logger.info("Starte HTTP...")
                    t.start()
                    self._http_server = server
                # Und jetzt einfach warten

                firstFrames = True
                while not self._doExit:
                    try:
                        camera.wait_recording(5)
                        pps = anal.processed / 5
                        anal.processed = 0
                        self.__logger.debug("Pro Sekunde verarbeitet: %d", pps)
                        if firstFrames:
                            def first_run():
                                self.__logger.info("Stream wird sich normalisiert haben. Queue wird angeschlossen...")
                                anal.run_queue( )
                            t = threading.Thread(target=first_run)
                            t.setDaemon(True)
                            t.run()
                            firstFrames = False
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
            txt_motion = "Bewegung" if self._inMotion else "."
            
            self._camera.annotate_text = txt_motion

            #self._camera.annotate_text = text1 + " {} {}APS {} {} {} {}".format(
            #    txt_motion, aps,
            #    self._lastState["x"], self._lastState["y"], self._lastState["val"], self._lastState["c"]
            #)

    def meassure_minimal_blocknoise(self):
        self.__logger.info("Starte neue Kalibrierung...")
        self._analyzer.states["still_frames"] = 0
        self._analyzer._calibration_running = True
        self._analyzer.framesToNoMotion *= 10

    def stop_record(self):
        if self._rtsp_recorder is not None:
            self._rtsp_recorder.shutdown()
            self._rtsp_recorder = None
        self._postRecordTimer = None

    def motion(self, motion:bool, data:dict, wasMeassureing:bool):
        if wasMeassureing:
            self._config["PiMotion/motion/blockMinNoise"] = self._analyzer.blockMaxNoise
            self._config["PiMotion/motion/frameMinNoise"] = self._analyzer.countMinNoise
        if motion:
            self.__logger.info("Motion")
            if self._config.get("PiMotion/record/enabled",True):
                path = self._config.get("PiMotion/record/path","~/Videos")
                path = "{}/{}.h264".format(path, dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                if self._postRecordTimer is None:
                    self._rtsp_recorder = self._rtsp_split.recordTo(path=path)
                else:
                    self._postRecordTimer.cancel()
                    self._postRecordTimer = None
                    self.__logger.debug("Aufname timer wird zurückgesetzt")
        else:
            self.__logger.info("No Motion")
            if self._postRecordTimer is not None:
                self._postRecordTimer.cancel()
                self._postRecordTimer = None
                self.__logger.debug("Aufname timer wird zurückgesetzt")
            self._postRecordTimer = threading.Timer(interval=self._config.get("PiMotion/motion/recordPost", 1), function=self.stop_record)
            self._postRecordTimer.start()
            self.__logger.debug("Aufnahme wird in {} Sekunden beendet.".format(self._config.get("PiMotion/motion/recordPost", 1)))
        self.motion_data(data)
        self._inMotion = motion
    
    def motion_data(self, data:dict):
        # x y val count
        self._lastState = {"motion": 1 if self._inMotion else 0, "x": data["hotest"][0],
            "y": data["hotest"][1], "val": data["hotest"][2], "c": data["noise_count"]}
        self._jsonOutput.write(self._lastState)
        self.update_anotation()
        if self._analyzer is not None and not self._analyzer._calibration_running:
            self.sendStates()
    
    def sendStates(self):
        self.__client.publish(self.topic.state, json.dumps(self._lastState))