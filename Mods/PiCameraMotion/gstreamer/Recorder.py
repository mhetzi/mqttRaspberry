# -*- coding: utf-8 -*-
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
except ValueError:
    raise ImportError()

from gi.repository import GObject, Gst, GstBase, GLib
import threading
import queue
import pathlib

import logging

GST_h264_PIPELINE_SUB = """
appsrc name=asrc is-live=true block=true format=GST_FORMAT_TIME !
video/x-h264, width={}, height={}, framerate={}/1 !
h264parse !
queue2 !
mp4mux name=mux fragment-duration=10 !
filesink location="{}"
appsrc name=subsrc!
text/x-raw,format=(string)utf8 !
mux.subtitle_0
"""

GST_h264_PIPELINE = """
appsrc name=asrc is-live=true block=true format=GST_FORMAT_TIME !
video/x-h264, width={}, height={}, framerate={}/1 !
h264parse !
queue2 !
mp4mux fragment-duration=10 !
filesink location="{}"
"""

GST_h264_PIPELINE_CLOCK = """
appsrc name=asrc is-live=true block=true format=GST_FORMAT_TIME caps=video/x-h264, framerate={}/1 !
h264parse ! clockoverlay time-format="%e.%m.Y %T halignment=right valignment=bottom text="{}" shaded-background=true font-desc="Sans, 36"" ! 
mp4mux ! filesink location={}
"""

class Recorder:

    def __init__(self, wh:tuple, fps: int, camName: str, path:pathlib.Path, logger:logging.Logger):
        GObject.threads_init()
        Gst.init(None)

        self.logger = logger

        self._hadSPS = False
        self.number_frames = 0
        self.fps = fps
        self.duration = 1 / self.fps * Gst.SECOND  # duration of a frame in nanoseconds

        pipeline_str = GST_h264_PIPELINE.format(int(wh[0]), int(wh[1]), int(fps), str(path.expanduser().absolute()))
        self.logger.debug("Gst Pipeline {}".format(pipeline_str))
        self.pipeline = Gst.parse_launch(pipeline_str)
        self._appsrc = self.pipeline.get_child_by_name('asrc')

        self._bus = self.pipeline.get_bus()
        self._bus.add_signal_watch()
        self._bus.enable_sync_message_emission()
        self._bus.connect("message", self.on_message)
    
    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.EOS:
            self.pipeline.set_state(Gst.State.NULL)
        elif t == Gst.MessageType.ERROR:
            self.pipeline.set_state(Gst.State.NULL)
            err, debug = message.parse_error()
            self.logger.warning("Error: {} Debug: {}".format(err, debug)) 
            self.stop()

    def writeFrame(self, data: bytes, frame: camf.PiVideoFrame, eof=False):
        buf = Gst.Buffer.new_allocate(None, len(data), None)
        buf.fill(0, data)
        buf.duration = self.duration
        timestamp = self.number_frames * self.duration
        buf.pts = buf.dts = int(timestamp)
        buf.offset = timestamp
        self.number_frames += 1
        self.pipeline.set_state(Gst.State.PLAYING)
        retval = self._appsrc.emit('push-buffer', buf)
        if retval != Gst.FlowReturn.OK:
            self.logger.error("push-buffer failed with \"{}\"".format(retval))
    
    def stop(self):
        self._appsrc.emit('end-of-stream')
        self.pipeline.set_state(Gst.State.NULL)
        del self._appsrc
        self.pipeline.unref()
        del self.pipeline