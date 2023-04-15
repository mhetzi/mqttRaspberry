from dasbus.loop import EventLoop
from threading import Thread
import threading

global _mutex
_mutex = threading.Lock()

global _COUNT
_COUNT = 0

global DBUS_INITED
DBUS_INITED=False

class EventLoopThread(Thread):
    loop = None

    def run(self) -> None:
        self.loop = EventLoop()
        self.loop.run()

global _DBUS_THREAD
_DBUS_THREAD: EventLoopThread = EventLoopThread()

def deinit_dbus():
    with _mutex:
        global _COUNT
        _COUNT = _COUNT - 1
        if _COUNT < 1:
            _DBUS_THREAD.loop.quit()
            _DBUS_THREAD.join()

def init_dbus():
    with _mutex:
        global _COUNT
        global __DBUS_INITED
        global _DBUS_THREAD
        
        _COUNT = _COUNT + 1

        if DBUS_INITED:
            return _DBUS_THREAD
        
        __DBUS_INITED = True

        _DBUS_THREAD = EventLoopThread()
        _DBUS_THREAD.setName("dasbus Event Loop")
        _DBUS_THREAD.start()
        return _DBUS_THREAD