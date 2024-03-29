# -*- coding: utf-8 -*-
# dependencies apt install libgstrtspserver-1.0-dev libgstrtspserver-1.0-0 gstreamer1.0-plugins-* python3-numpy cython3 make cmake
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

Gst.init(None)


class CameraSplitIO(threading.Thread):
    file = None
    logger = None
    _closed = False
    _reopen = True
    _queue = None
    _hadSPS = False
    _oldAppend = None
    _io = None
    _splitter_port = None
    _endRecording = False
    _myParent = None

    def __init__(self, camera: cam.PiCamera, splitter_port=1):
        threading.Thread.__init__(self)
        self._camera = camera
        self._queue = queue.Queue(10)
        self._splitter_port = splitter_port
        self.lock = threading.Lock()
        self.append = self._append

    def open_named_pipe(self):
        self.init_named_pipe(False)

    def init_named_pipe(self, delete=True):
        try:
            # self.logger.debug("mkfifo()")
            os.mkfifo("/tmp/motion-gst-pipe")
        except FileExistsError:
            # self.logger.warning("FileExists")
            if delete:
                try:
                    os.remove("/tmp/motion-gst-pipe")
                    self.logger.debug("mkfifo() 2")
                    os.mkfifo("/tmp/motion-gst-pipe")
                except FileExistsError:
                    self.logger.warning("FileExists 2")
        # self.logger.debug("open()")
        self.file = open("/tmp/motion-gst-pipe", mode="wb")
        # self.fill_rtsp_stream()
        delete = False

    def _restore_append(self):
        self.append = self._append
        

    def _append(self, item: bytes):
        self._oldAppend(item)

        encoder = self._camera._encoders[self._splitter_port]
        frame = None
        if encoder.frame.complete:
            frame = encoder.frame
        if frame is None:
            pass
        #elif frame.timestamp is None and frame.frame_type != camf.PiVideoFrameType.sps_header and self._myParent is None:
        #    self.logger.debug("frame timestamp is None")
        elif not self.is_alive():
            pass
        else:
            if not self._hadSPS:
                with self.lock:
                    if frame.frame_type == camf.PiVideoFrameType.sps_header:
                        try:
                            self._queue.put_nowait(item)
                            self._hadSPS = True
                        except queue.Full:
                            self.logger.debug("queue.Full on append()")
                            if self._myParent is not None and not self.is_alive():
                                self.logger.warning("Recorder here. Lebe ja gar nicht mehr! Shutdown wird wiederholt...")
                                self.shutdown()
            else:
                try:
                    self._queue.put_nowait(item)
                except:
                    self._hadSPS = False
                    self.logger.warning("Stream full. Clear buffer and wait for new SPS")
                    try:
                        while True:
                            self._queue.get_nowait()
                    except queue.Empty:
                        if self._myParent is not None and not self.is_alive():
                            self.logger.warning("Recorder here. Lebe ja gar nicht mehr! Shutdown wird wiederholt...")
                            self.shutdown()
                    pass

    def _redirectPackages(self, io: cams.PiCameraCircularIO, file):
        self.logger.debug("Überschreibe append methode")
        self._oldAppend = io._data.append if self._myParent is None else self._myParent.append
        self._io = io
        io._data.append = self.append
        if file is not None:
            self.logger.debug(
                "file Variable angegeben, deaktiviere neu öffnen")
            self.file = file
            self._reopen = False

    def initAndRun(self, cameraStream: cams.PiCameraCircularIO, file=None, parent=None):
        self.logger = self.logger.getChild(
            "RTSP") if file is None else self.logger.getChild("Record"
        )
        self._myParent = parent
        self._redirectPackages(cameraStream, file)
        self.name = "cam_RTSP_queue" if file is None else "cam_file_queue"
        self.setDaemon(False)
        self.start()
        if parent is not None:
            try:
                with self.lock:
                    with cameraStream.lock:
                        save_pos = cameraStream.tell()
                        try:
                            pos = cameraStream._find_all(
                                camf.PiVideoFrameType.sps_header)
                            if pos is not None:
                                cameraStream.seek(pos)
                                while True:
                                    buf = cameraStream.read1()
                                    if not buf:
                                        break
                                    self._queue.put(buf)
                        finally:
                            cameraStream.seek(save_pos)
                            cameraStream.clear()
            except:
                self.logger.exception("Konnte anfang nicht speichern")

    def shutdown(self):
        self._closed = True
        self.logger.info("Beende Queue")
        self.join(3)
        if self.is_alive() and self._reopen:
            self.logger.warning("Queue still alive")
            with open("/tmp/motion-gst-pipe", mode="rb") as f:
                pass
        elif self.is_alive() and not self._reopen:
            self.file.flush()
            self.file.close()
        self.join()
        self.logger.info("Queue beendet")
        if not self._hadSPS:
            self.logger.error("Hatte kein SPS Frame!")
        self.logger.debug("Restore append method")
        if self._myParent is None:
            self._io._data.append = self._oldAppend
        else:
            self._myParent.append = self._oldAppend
            self._myParent._restore_append()

    def run(self):
        if self.file is None:
            self.logger.debug("Kein File, erstelle und öffne")
            self.init_named_pipe()
        item = None
        self.logger.info("Beginne mit weitergabe der queued frames...")
        while not self._closed:
            try:
                if item is not None:
                    self.file.write(item)
                    item = None
            except BrokenPipeError:
                if not self._reopen:
                    self.logger.warning(
                        "reopen ist False, beende queue thread")
                    break
                self.logger.info("BrokenPipe. öffne NamedPipe erneut")
                self.open_named_pipe()
                self._hadSPS = False
                continue
            try:
                item = self._queue.get(timeout=5)
                if item is None:
                    self.logger.warning("In der queue war ein None Object!")
            except queue.Empty:
                self.logger.warning("Es war kein Frame in der Queue!")

    def recordTo(self, path=None, stream=None, preRecordSeconds=1):
        if path is None and stream is None:
            self.logger.error("Pfad und Stream ist None!")
            return
        if path is not None and stream is None:
            self.logger.info("Öffne {} um Aufnahme zu speichern".format(path))
            stream = open(path, "wb", buffering=(
                17000000 * (preRecordSeconds+1) // 8))
        new_splitter = CameraSplitIO(self._camera, self._splitter_port)
        new_splitter.logger = self.logger
        new_splitter.initAndRun(self._io, file=stream, parent=self)
        return new_splitter


class GstRtspPython:

    def __init__(self, framerate, camName=""):
        self.__ml = None
        self.__srv = None
        self.__fac = None
        self.logger = None
        self._fps = framerate
        self._camName = camName
        self._clients = {}

    def runServer(self):
        self.logger.info("Server wird gestartet")
        self.__ml = GLib.MainLoop()
        self.__srv = GstRtspServer.RTSPServer()
        self.__srv.connect("client-connected",  self.client_connected_call)
        mounts = self.__srv.get_mount_points()
        self.__fac = GstRtspServer.RTSPMediaFactory()
        self.__srv.set_address("0.0.0.0")
        self.__fac.set_shared(True)
        # Bitrate * Sekunden // 8
        self.__fac.set_buffer_size((17000000 * 1 // 8) ) # was // 8 )/2)
        self.__fac.set_latency(250)
        self.__fac.set_launch(
            '( filesrc location=/tmp/motion-gst-pipe do-timestamp=true ! video/x-h264, framerate={}/1 ! h264parse ! rtph264pay name=pay0 pt=96 )'.format(self._fps))
        mounts.add_factory("/h264", self.__fac)
        
        self.__srv.attach(None)
        self.__ml.run()
        self.logger.info("Server beendet")

    def stopServer(self):
        self.__ml.quit()
        self.logger.info("Server wird beendet")
    
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
