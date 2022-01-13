# -*- coding: utf-8 -*-
# dependencies apt install libgstrtspserver-1.0-dev libgstrtspserver-1.0-0 gstreamer1.0-plugins-* gstreamer1.0-omx python3-numpy cython3 make cmake
try:
    import picamera as cam
    import picamera.array as cama
    import picamera.streams as cams
    import picamera.frames as camf

except ImportError:
    import Mods.referenz.picamera.picamera as cam
    import Mods.referenz.picamera.picamera.streams as cams
    import Mods.referenz.picamera.picamera.array as cama
    import Mods.referenz.picamera.picamera.frames as camf
try:
    import gi
    gi.require_version("Gst", "1.0")
    gi.require_version('GstBase', '1.0')
    gi.require_version('GstRtspServer', '1.0')
except ValueError:
    raise ImportError()

from gi.repository import GObject, Gst, GstBase, GstRtspServer, GLib, GstRtsp
import os
import io
import threading
import time
import queue
import pathlib
from weakref import ref

import logging

from  Mods.PiCameraMotion.gstreamer.SplitStream import CameraSplitter


GST_h264_PIPELINE_CLOCK = """
appsrc name=asrc is-live=true block=true format=GST_FORMAT_TIME !
video/x-h264, framerate={}/1 !
h264parse !
queue !
decodebin !
clockoverlay time-format="%e.%m.%Y %T" halignment=right valignment=bottom text="{}" shaded-background=true font-desc="Sans, 16" ! 
queue !
x264enc speed-preset=superfast key-int-max=15 !
video/x-h264,width={},height={},framerate={}/1,profile=baseline !
h264parse !
video/x-h264,stream-format="byte-stream" !
rtph264pay name=pay0 pt=96
"""

GST_h264_PIPELINE = """
appsrc name=asrc is-live=true block=true format=GST_FORMAT_TIME !
video/x-h264, framerate={}/1 !
h264parse !
rtph264pay name=pay0 pt=96 {}
"""

class AppSource(threading.Thread):
    __sleeping = 0

    def __init__(self, fps:int, log: logging.Logger, splitter: CameraSplitter, parent=None, appSrc=None, **properties):
        super(AppSource, self).__init__(**properties)
        threading.Thread.__init__(self)
        self.number_frames = 0
        self.fps = fps
        self.duration = 1 / self.fps * Gst.SECOND  # duration of a frame in nanoseconds
        self.logger = log
        self._queue = queue.Queue(int(fps*1.5))
        self._doShutdown = False
        self._sendData = threading.Event()
        self._sendData.clear()
        self._lock = threading.Lock()
        self._hadSPS = False
        self.setName("Camera_RTSP_AppSrc")
        self._camera_splitter = ref(splitter)
        self.parent = ref(parent)
        self._split_id = self._camera_splitter().add(self.writeFrame)
        self._appsrc = appSrc

    def on_need_data(self, src, lenght):
        #self.logger.debug("need_data have approx. {} data packets.".format(self._queue.qsize()))
        self._sendData.set()
    
    def on_enough_data(self, src):
        self._sendData.clear()
        #self.logger.debug("enough_data")
        self._hadSPS = True

    def mainloop(self):
        while True:
            if not self._sendData.is_set():
                if not self._sendData.wait(5.0):
                    if self._doShutdown:
                        self.logger.info("OK Wird beendet")
                        break
                    self.__sleeping += 1
                    if self.__sleeping > 100:
                        self.logger.warning("Schlafe seit 100 Warte zyklen. Beende...")
                        self.stopThread()
                    continue
            if self._doShutdown:
                self.logger.info("OK Wird beendet")
                break
            try:
                data, frame = self._queue.get(timeout=5)
            except queue.Empty:
                self.logger.warning("Queue underrun")
                continue
            buf = Gst.Buffer.new_allocate(None, len(data), None)
            buf.fill(0, data)
            buf.duration = self.duration
            try:
                timestamp = self.number_frames * self.duration if frame is None or frame.timestamp is None else frame.timestamp
                timestamp = self.number_frames * self.duration
                buf.pts = buf.dts = int(timestamp)
                buf.offset = timestamp
            except:
                timestamp = self.number_frames * self.duration
                buf.pts = buf.dts = int(timestamp)
                buf.offset = timestamp
            self.number_frames += 1
            try:
                retval = self._appsrc.emit('push-buffer', buf)
                self.__sleeping = 0
                if retval == Gst.FlowReturn.FLUSHING:
                    self.logger.debug("Gst Flushing")
                    self.on_enough_data(None)
                    self.stopThread()
                elif retval != Gst.FlowReturn.OK:
                    self.logger.error("push-buffer failed with \"{}\"".format(retval))
                    self.stopThread()
            except:
                self.logger.exception("push-buffer failed!")
        try:
            self._appsrc.emit('end-of-stream')
        except AttributeError:
            pass

    def run(self):
        try:
            self.mainloop()
        except:
            self.logger.exception("RTSP AppSource MainLoop error")
        self.logger.debug("Queue wird geleert...")
        self._queue.queue.clear()

    def writeFrame(self, data: bytes, frame: camf.PiVideoFrame, eof=False):
        with self._lock:
            if eof:
                self.logger.info("Warning EOF found! Beende Thread...")
                self.stopThread()
            if frame is not None:
                if frame.frame_type == camf.PiVideoFrameType.sps_header and not self._hadSPS:
                    #self.logger.debug("SPS")
                    self._hadSPS = True
                    try:
                        self._queue.put((data, frame), timeout=0.15)
                    except queue.Full:
                        self._hadSPS = False
                    return
                elif frame.frame_type != camf.PiVideoFrameType.sps_header and not self._hadSPS:
                    #self.logger.debug("Ignoreing frame cause no sps and had no sps")
                    return
            elif frame is None and not self._hadSPS:
                if self.__sleeping < self.fps:
                    self.logger.warning("Kein frame und hatte noch kein SPS")
            
            try:
                self._queue.put_nowait((data,frame))
            except queue.Full:
                if self._sendData.isSet():
                    self._queue.put((data, frame), block=True, timeout=0.25)
                    return
                self._hadSPS = False
                try:
                    while True:
                        self._queue.get_nowait()
                except queue.Empty:
                    #self.logger.debug("Cleared after overrun")
                    pass
    
    def stopThread(self):
        self._camera_splitter().remove(self._split_id)
        self.logger.info("Beende Thread")
        self._doShutdown = True
        self._sendData.set()
        try:
            self._appsrc.emit('end-of-stream')
        except AttributeError:
            pass
        self.logger.info("Warte auf beendigung")
        try:
            self.join()
        except RuntimeError:
            pass
        self.parent().stopThread(self)


class PiCameraMediaFactory(GstRtspServer.RTSPMediaFactory, threading.Thread):
    def __init__(self, fps:int, CamName:str, log: logging.Logger, splitter: CameraSplitter, wh=None, **properties):
        super(PiCameraMediaFactory, self).__init__(**properties)
        threading.Thread.__init__(self)
        self.number_frames = 0
        self.fps = fps
        self.duration = 1 / self.fps * Gst.SECOND  # duration of a frame in nanoseconds
        self.launch_string = GST_h264_PIPELINE.format(self.fps, "aggregate-mode=zero-latency")
        if wh is not None:
            self.launch_string = GST_h264_PIPELINE_CLOCK.format(self.fps, CamName, wh[0], wh[1], int(self.fps/2))
        self.logger = log
        self._queue = queue.Queue(int(fps*1.5))
        self._camera_splitter = ref(splitter)
        self.set_eos_shutdown(True)
        self._threads = []

    def do_create_element(self, url):
        try:
            self.logger.debug("do_create_element url: {} with {}".format(url.decode_path_components(), self.launch_string))
            return Gst.parse_launch(self.launch_string)
        except:
            self.launch_string = GST_h264_PIPELINE.format(self.fps, "")
            self.logger.debug("do_create_element url: {} with {}".format(url.decode_path_components(), self.launch_string))
            return Gst.parse_launch(self.launch_string)

    def do_configure(self, rtsp_media):
        self.number_frames = 0
        appsrc = rtsp_media.get_element().get_child_by_name('asrc')
        new_appSrc = AppSource(
            fps=self.fps,
            log=self.logger.getChild("AppSrc"),
            splitter=self._camera_splitter(),
            parent=self,
            appSrc=appsrc
        )
        appsrc.connect('need-data', new_appSrc.on_need_data)
        appsrc.connect('enough-data', new_appSrc.on_enough_data)
        new_appSrc.start()
        self._threads.append(new_appSrc)
    
    def stopThread(self, thread=None):

        if thread:
            try:
                self._threads.remove(thread)
            except ValueError:
                pass
            return

        for t in self._threads:
            t.stopThread()


class GstServer( GstRtspServer.RTSPServer, threading.Thread ):
    def __init__(self, factory:GstRtspServer.RTSPMediaFactory, logger: logging.Logger, **properties):
        super(GstServer, self).__init__(**properties)
        threading.Thread.__init__(self)
        
        self._clients = {}
        self.logger = logger.getChild("GstRtspServer")
        
        Gst.init(None)
        self._mainLoop = GObject.MainLoop()

        self.factory = factory
        self.factory.set_shared(True)
        self.get_mount_points().add_factory("/h264", self.factory)
        self.set_address("0.0.0.0")
        self._gst_id = self.attach(None)
        self.connect("client-connected",  self.client_connected_call)
        self.setName("GstRtspServerThread")

    def run(self):
        self._mainLoop.run()

    def runServer(self):
        self.factory.start()
        self.start()

    def stopServer(self):
        self.logger.info("Server wird beendet")
        self._mainLoop.quit()
        self.factory.stopThread()
    
    def client_connected_call(self, srv: GstRtspServer.RTSPServer, client: GstRtspServer.RTSPClient):
        try:
            con = client.get_connection()
            ip = con.get_ip()
            sig = client.connect("closed",  self.client_closed)
            self._clients[client] = (ip, sig)
            self.logger.info("Neuer Client {} verbunden".format(ip))
        except:
            self.logger.exception("Fehler beim abrufen der IP")
    
    def client_closed(self, c: GstRtspServer.RTSPClient):
        ip, sig = self._clients.get(c, (None,None))
        c.disconnect(sig)
        self.logger.info("Verbindung von {} geschlossen!".format(ip))