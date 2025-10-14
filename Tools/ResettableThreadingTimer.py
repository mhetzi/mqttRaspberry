from threading import Thread, Event
from typing import Callable

class Timer(Thread):
    """Call a function after a specified number of seconds:

            t = Timer(30.0, f, args=None, kwargs=None)
            t.start()
            t.cancel()     # stop the timer's action if it's still waiting

    """

    def __init__(self, interval, function, args=None, kwargs=None):
        Thread.__init__(self)
        self.interval = interval
        self.function = function
        self.args = args if args is not None else []
        self.kwargs = kwargs if kwargs is not None else {}
        self.finished = Event()
        self.rerun = Event()
    
    def reset(self) -> bool:
        if self.finished.is_set():
            return False
        if not self.is_alive():
            self.start()
        self.rerun.set()
        self.finished.set()
        return True

    def cancel(self):
        """Stop the timer if it hasn't finished yet."""
        self.finished.set()

    def run(self):
        while self.rerun.is_set():
            self.rerun.clear()
            self.finished.wait(self.interval)
            if not self.finished.is_set():
                self.function(*self.args, **self.kwargs)
            self.finished.set()

class ManagedTimer:
    __slots__=("_timer", "name", "interval", "func")

    _timer: Timer
    name: str
    interval: float
    func: Callable[[], None]

    def __init__(self, func:Callable[[], None], interval=30.5) -> None:
        self.func = func
        self.interval = interval
        self.name = ""
        self._timer = Timer(self.interval, self.func)
    
    def reset(self):
        if not self._timer.reset():
            self._timer = Timer(self.interval, self.func)
            self._timer.reset()
    
    def cancel(self):
        self._timer.cancel()
