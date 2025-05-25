from dasbus.loop import EventLoop
from threading import Thread
import threading
import logging

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

def deinit_dbus(logger:logging.Logger | None = None):
    with _mutex:
        global _COUNT
        _COUNT = _COUNT - 1
        if logger is not None:
            logger.debug(f"Dbus has {_COUNT} remaining consumers.")
        if _COUNT < 1 and _DBUS_THREAD.loop is not None:
            if logger is not None:
                logger.debug(f"Dbus has no consumers. Quitting...")
            _DBUS_THREAD.loop.quit()
            _DBUS_THREAD.join(5)
            if logger is not None:
                logger.debug(f"Dbus has no consumers. Quitted? {_DBUS_THREAD.is_alive()=}")
            global DBUS_INITED
            DBUS_INITED = False

def init_dbus(logger:logging.Logger | None = None):
    with _mutex:
        global _COUNT
        global DBUS_INITED
        global _DBUS_THREAD
        
        _COUNT = _COUNT + 1

        if DBUS_INITED:
            if logger is not None:
                logger.debug(f"Have dasbus event loop: {DBUS_INITED=} {_COUNT=}")
            return _DBUS_THREAD
        
        if logger is not None:
            logger.debug(f"Start new dasbus event loop: {DBUS_INITED=} {_COUNT=}")
        DBUS_INITED = True

        _DBUS_THREAD = EventLoopThread()
        _DBUS_THREAD.setName("dasbus Event Loop")
        _DBUS_THREAD.start()
        return _DBUS_THREAD