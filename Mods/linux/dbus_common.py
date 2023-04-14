from dasbus.loop import EventLoop
from threading import Thread

class EventLoopThread(Thread):
    def run(self) -> None:
        loop = EventLoop()
        loop.run()

DBUS_INITED=False
__DBUS_THREAD = None
def init_dbus():
    if DBUS_INITED:
        return __DBUS_THREAD
    
    __DBUS_INITED = True

    __DBUS_THREAD = EventLoopThread()
    __DBUS_THREAD.setName("dasbus Event Loop")
    __DBUS_THREAD.start()
    return __DBUS_THREAD