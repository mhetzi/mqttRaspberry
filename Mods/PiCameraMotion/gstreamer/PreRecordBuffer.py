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

from Mods.PiCameraMotion.gstreamer.Recorder import Recorder
from Mods.PiCameraMotion.gstreamer.SplitStream import CameraSplitter

import threading
import queue
import pathlib
from datetime import datetime
import logging
from weakref import ref

class PreRecordBuffer(threading.Thread):
    
    def __init__(self, secs_pre:float, wh:tuple, fps: int, camName: str, path:pathlib.Path, splitter:CameraSplitter, logger:logging.Logger):
        threading.Thread.__init__(self, target=self._thread_run)
        self.setName("PreRecordBuffer")

        self._fps = fps
        self._camName = camName
        self._path = path

        self._queue = queue.Queue(int(secs_pre * fps))
        self.logger = logger.getChild("PreRecordBuffer")
        self._thread = threading.Thread(name="PreRecord", daemon=False, target=self._thread_run)
        self._do_transmit = threading.Event()
        self._do_transmit.clear()
        self._lock = threading.Lock()
        self.recorder = None
        self._do_thread_run = True
        self._hadSPS = False
        self._splitter = ref(splitter)
        self._spliiter_id = self._splitter().add(self.writeFrame)
        self._wh = wh

    def _thread_run(self):
        while self._do_thread_run:
            if not self._do_transmit.is_set() and self.recorder is not None:
                self.recorder.stop()
                self.recorder = None
                self.logger.debug("Aufnahme gestoppt")
            elif self._do_transmit.is_set() and self.recorder is None:
                path = self._path.joinpath(
                    "aufnahmen",
                    "{}.mp4".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
                self.logger.info("Fabricating new Recorder with path {}".format(path))
                self.recorder = Recorder(fps=self._fps, camName=self._camName, path=path, logger=self.logger, wh=self._wh)
            if self._do_transmit.wait(5.0):
                if self.recorder is None:
                    continue
                try:
                    data, frame = self._queue.get(timeout=5)
                    self.recorder.writeFrame(data, frame)
                except queue.Empty:
                    pass
    
    def record(self):
        self.logger.debug("Aufnahme wird freigegeben...")
        self._do_transmit.set()
    
    def stop_recording(self):
        self._do_transmit.clear()
    
    def destroy(self):
        self._do_thread_run = False
        self._do_transmit.set()
        if self.recorder is not None:
            self.recorder.stop()
            self.recorder = None
        self._splitter().remove(self._spliiter_id)
        self.join()

    def writeFrame(self, data: bytes, frame: camf.PiVideoFrame, eof=False):
        with self._lock:
            if frame is not None:
                if frame.frame_type == camf.PiVideoFrameType.sps_header and not self._hadSPS:
                    self._hadSPS = True
                    self._queue.put((data, frame))
                    #self.logger.debug("SPS")
                elif frame.frame_type != camf.PiVideoFrameType.sps_header and not self._hadSPS:
                    return
            
            try:
                self._queue.put(item=(data, frame), block=self._do_transmit.is_set())
            except queue.Full:
                self._hadSPS = False
                #self.logger.debug("NO_SPS")
                try:
                    while True:
                        self._queue.get_nowait()
                except queue.Empty:
                    pass