import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib
__global_glibthread = None

import threading

class GlibThread(threading.Thread):
    def __init__(self):
        super().__init__(name="upower_ml", daemon=False)
        self.loop = GLib.MainLoop()
        self.locked = 0
    
    #Only starts Thread if not alive
    def safe_start(self):
        if not self.is_alive():
            self.start()

    """ shutdown decrements instance locks """
    def add_instance_lock(self):
        self.locked += 1
        return self

    def run(self):
        self.loop.run()

    def join(self):
        if self.locked > 0:
            return
        return super().join()

    def shutdown(self):
        self.locked -= 1
        if self.locked > 0:
            return
        self.loop.quit()
    
    @staticmethod
    def getThread():
        global __global_glibthread

        if isinstance(__global_glibthread, GlibThread):
            return __global_glibthread
        glibthread = GlibThread()
        return glibthread

__DBUS_INITED=False
def init_dbus():
    global __DBUS_INITED
    if __DBUS_INITED:
        return
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
    __DBUS_INITED = True