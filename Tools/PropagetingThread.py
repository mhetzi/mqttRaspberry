from threading import Thread

class PropagatingThread(Thread):
    exc = None
    ret = None
    
    def run(self):
        self.exc = None
        try:
            if hasattr(self, '_Thread__target'):
                # Thread uses name mangling prior to Python 3.
                self.ret = self._Thread__target(*self._Thread__args, **self._Thread__kwargs)
            else:
                self.ret = self._target(*self._args, **self._kwargs)
        except BaseException as e:
            self.exc = e

    def join(self, timeout=None):
        super(PropagatingThread, self).join(timeout)
        if self.exc:
            raise self.exc
        return self.ret

VanillaThread = None

def installProagetingThread():
    import threading
    global VanillaThread
    VanillaThread = threading.Thread

    threading.Thread = PropagatingThread
    pass