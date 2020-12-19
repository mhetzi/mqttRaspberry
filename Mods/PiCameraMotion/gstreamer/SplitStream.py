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
import logging
from io import BytesIO

class CameraSplitter(cams.PiCameraCircularIO):
    
    def __init__(self, camera: cam.PiCamera, log: logging.Logger, splitter_port=0, mjpeg_mode=False):
        self._callbacks = {}
        self.log = log.getChild("CameraSplitter" if not mjpeg_mode else "CameraSplitterMJPEG")
        self.splitter_port = splitter_port
        self._camera = camera
        self._blockEof = True
        self.written = 0
        #self.fps = 0
        #import schedule
        #def show_fps():
        #    self.log.debug("FPS:{}".format(self.fps))
        #    self.fps = 0
        #schedule.every(1).second.do(show_fps)
        self.adapter = self._mjpeg_adapter if mjpeg_mode else self._adapter
        self.buffer = BytesIO() if mjpeg_mode else None

    def add(self, func, customID=None):
        if not callable(func):
            raise Exception("Not a callable")
        import uuid
        while True:
            if customID is None:
                id = str(uuid.uuid4())
            else:
                id = customID
            if id not in self._callbacks.keys():
                self._callbacks[id] = func
                break
            elif customID is not None:
                raise Exception("Custom ID {} ist bereits regestriert!".format(customID))
        self.log.debug("Added new callback with id {} ".format(id))
        return id
    
    def remove(self, id: str):
        try:
            del self._callbacks[id]
            self.log.info("Callback {} erfolgreich entfernt".format(id))
        except:
            pass
    
    def dispatch(self, item: bytes, frame: camf.PiVideoFrame):
        try:
            for c in self._callbacks.keys():
                try:
                    self._callbacks[c](item, frame)
                except:
                    self.log.exception("Dispatching frame to {} failed.".format(c))
        except RuntimeError:
            pass

    def _adapter(self, item:bytes):
        encoder = self._camera._encoders[self.splitter_port]
        frame = None
        if encoder.frame.complete:
            frame = encoder.frame
        self.dispatch(item, frame)
        return len(item)
    
    def _mjpeg_adapter(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            try:
                item = self.buffer.getvalue()
                #self.log.debug("MJPEG Dispatch")
                self.dispatch(item, None)
                self.written = 0
            except: self.log.exception()
            self.buffer.seek(0)
        return self.buffer.write(buf)

    def write(self, b):
        if self.written < 254:
            self.written += 1
        else:
            self.written = 0
        #self.log.debug("write {} bytes".format(len(b)))
        leng = self.adapter(b)
        self._blockEof = False
        return leng
    
    def flush(self):
        if self._blockEof:
            return
        try:
            for c in self._callbacks.keys():
                try:
                    self._callbacks[c](None, None, eof=True)
                except:
                    self.log.exception("Dispatching EndOfFile to {} failed.".format(c))
        except RuntimeError:
            self.flush()