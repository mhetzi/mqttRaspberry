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
        payload = self.topic.get_config_payload(sensorName, "", unique_id=uid, value_template="{{ value_json.motion }}")
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

            with analyzers.Analyzer(camera) as anal:
                self.__logger.debug("Analyzer erstellt")
                anal.motion_call = lambda motion, data: self.motion(motion, data)
                anal.motion_data_call = lambda data: self.motion_data(data)
                anal.frameToTriggerMotion = self._config.get("PiMotion/motion/motion_frames", 4)
                anal.framesToNoMotion = self._config.get("PiMotion/motion/still_frames", 4)
                anal.minNoise = self._config.get("PiMotion/motion/minNoise", 1000)
                anal.logger = self.__logger.getChild("Analyzer")

                self._circularStream = cam.PiCameraCircularIO(camera, seconds=self._config["PiMotion/motion/recordPre"])

                if self._config.get("PiMotion/rtsp/enabled", True):
                    self.__logger.debug("Erstelle CameraSplitIO")
                    rtsp_split = rtsp.CameraSplitIO(camera)
                    self._rtsp_split = rtsp_split
                    rtsp_split.logger = self.__logger.getChild("RTSP")
                    rtsp_split.initAndRun(self._circularStream, file=None)
                    self.__logger.info("Aktiviere RTSP...")
                    rtsp_server = rtsp.GstRtspPython(self._config.get("PiMotion/camera/fps", 23))
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

                    server = httpc.StreamingServer(address, httpc.makeStreamingHandler(http_out, self._jsonOutput, pic_out))
                    camera.start_recording(http_out, format='mjpeg', splitter_port=2)
                    server.logger = self.__logger.getChild("HTTP_srv")
                    t = threading.Thread(name="http_server", target=server.run)
                    self.__logger.info("Starte HTTP...")
                    t.start()
                    self._http_server = server
                # Und jetzt einfach warten

                while not self._doExit:
                    try:
                        camera.wait_recording(2)
                        pps = anal.processed / 2
                        anal.processed = 0
                        self.__logger.debug("Pro Sekunde verarbeitet: %d", pps)
                        self.update_anotation(aps=pps)

                    except:
                        self.__logger.exception("Kamera Fehler")
                        exit(-1)
        server.server_close()
        camera.stop_recording(splitter_port=2)
        camera.stop_recording()
        self._camera = None

    def update_anotation(self, aps=0):
        if self._camera is not None:
            text1 = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            txt_motion = "Bewegung" if self._inMotion else "."
            
            self._camera.annotate_text = text1 + " " + txt_motion

            #self._camera.annotate_text = text1 + " {} {}APS {} {} {} {}".format(
            #    txt_motion, aps,
            #    self._lastState["x"], self._lastState["y"], self._lastState["val"], self._lastState["c"]
            #)


    def motion(self, motion:bool, data:dict):
        if motion == self._inMotion:
            return
        if motion:
            self.__logger.info("Motion")
            self._inMotion = True
        self.__logger.info("No Motion")
        self._inMotion = False
        self.motion_data(data)
        self.sendStates()
    
    def motion_data(self, data:dict):
        # x y val count
        self._lastState = {"motion": 1 if self._inMotion else 0, "x": data["hotest"][0],
            "y": data["hotest"][1], "val": data["hotest"][2], "c": data["noise_count"]}
        self._jsonOutput.write(self._lastState)
        #self.update_anotation()
    
    def sendStates(self):
        self.__client.publish(self.topic.state, json.dumps(self._lastState))