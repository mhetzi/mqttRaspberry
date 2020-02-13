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
    gi.require_version('GstRtspServer', '1.0')
except ValueError:
    raise ImportError()

from gi.repository import GObject, Gst, GstBase, GstRtspServer, GLib, GstRtsp
import os
import io
import threading
import time
import queue
import subprocess
import logging

Gst.init(None)

class CameraSplitter(cam.CircularIO);
    
    def __init__(self, frames_to_sps: int, log: logging.Logger):
        self._queue = queue.Queue(maxsize=frames_to_sps + 2)

    def 
