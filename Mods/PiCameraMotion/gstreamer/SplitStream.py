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

class CameraSplitter(cams.PiCameraCircularIO):
    
    def __init__(self, camera: cam.PiCamera, log: logging.Logger, splitter_port=0):
        self._callbacks = {}
        self.log = log.getChild("CameraSplitter")
        self.splitter_port = splitter_port
        self._camera = camera
        self._blockEof = True

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

    def adapter(self, item:bytes):
        encoder = self._camera._encoders[self.splitter_port]
        frame = None
        if encoder.frame.complete:
            frame = encoder.frame
        self.dispatch(item, frame)

    def write(self, b):
        #self.log.debug("write {} bytes".format(len(b)))
        self.adapter(b)
        self._blockEof = False
        return len(b)
    
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