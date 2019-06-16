# -*- coding: utf-8 -*-
try:
    import picamera as cam
    import picamera.array as cama
except ImportError:
    import Mods.referenz.picamera.picamera as cam
    import Mods.referenz.picamera.picamera.array as cama

import gi
gi.require_version("Gst", "1.0")
gi.require_version('GstVideo', '1.0')
gi.require_version('GstRtspServer', '1.0')

from gi.repository import GObject, Gst, GstBase, GstVideo, GstRtspServer, GstPushSrc

Gst.init(None)

def generateRtspServer(s: cam.PiCameraCircularIO):
    class GstRtspPython(GstBase.PushSrc):
        GST_PLUGIN_NAME = "pi_circ_src"

        def __init__(self):
            self.__ml = None
            self.__srv = None
            self.__fac = None
            self.set_live(True)

        def create(self, b: Gst.Buffer):
            try:
                if s.readable is True:
                    data = s.read1()
                    buf = Gst.Buffer.new_wrapped_full(
                        Gst.MemoryFlags.READONLY,
                        data,
                        len(data),
                        0,
                        None,
                        None
                    )
                    b = buf
                    return Gst.FlowReturn.OK
                else:
                    return Gst.FlowReturn.EOS
            except ValueError:
                return Gst.FlowReturn.EOS
            except return Gst.FlowReturn.ERROR

        def runServer(self):
            self.__ml = GObject.MainLoop()
            self.__srv = GstRtspServer.RTSPServer()
            mounts = self.__srv.get_mount_points()
            self.__fac = GstRtspServer.RTSPMediaFactory()
            self.__srv.set_address("0.0.0.0")
            self.__fac.set_shared(True)
            self.__fac.set_launch('( pi_circ_src ! x264enc speed-preset=ultrafast tune=zerolatency ! rtph264pay name=pay0 pt=96 )')
            mounts.add_factory("/test", sefl.__fac)
            self.__srv.attach(None)

    GObject.type_register(GstRtspPython)
    __gstelementfactory__ = (GstRtspPython.GST_PLUGIN_NAME, Gst.Rank.NONE, GstRtspPython)
    return GstRtspPython()
