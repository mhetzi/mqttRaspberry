import dbus

from typing import IO, Union
import logging
import json
import os
import threading
import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib

from time import sleep

class GlibThread(threading.Thread):
    def __init__(self):
        super().__init__(name="logind_ml", daemon=False)
        self.loop = GLib.MainLoop()
    def run(self):
        self.loop.run()
    def shutdown(self):
        self.loop.quit()

thread_gml = GlibThread()
_mainloop = None

from dbus.mainloop.glib import DBusGMainLoop
_mainloop = DBusGMainLoop(set_as_default=True)
import dbus.mainloop.glib as gml
gml.threads_init()

_bus    = dbus.SystemBus(mainloop=_mainloop)
_session_bus = dbus.SessionBus(mainloop=_mainloop)


def printer(*args, **kwargs):
    print("Signal begin:")
    for arg in args:
        print("Next argument through *argv :", arg)
    for key, value in kwargs.items():
        print ("%s == %s" %(key, value))
    print("==== SIGNAL END =====")

_session_bus.add_signal_receiver(printer)

try:
    thread_gml.loop.run()
except:
    pass
thread_gml.loop.quit()