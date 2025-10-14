from threading import Thread, Event
from typing import Callable
import logging

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
        self.logger: logging.Logger | None = None
    
    def reset(self) -> bool:
        self.rerun.set() # Dont let thread die
        if self.finished.is_set():
            return False # Thread is done, cant reover
        if not self.is_alive():
            self.start() # Thread was not alive, unitl now
        else:
            self.finished.set() # Timer was counting, cancel counting...
        return True

    def cancel(self):
        """Stop the timer if it hasn't finished yet."""
        self.finished.set()

    def run(self):
        if self.logger is not None:
            self.logger.debug("Begin Timer...")
        while self.rerun.is_set():
            self.rerun.clear() # Dont endlessly loop, when ther is  no request
            self.finished.clear()
            self.finished.wait(self.interval)
            if not self.finished.is_set(): # Timedout, no reset received. Action!
                self.function(*self.args, **self.kwargs)
            self.finished.set()
        if self.logger is not None:
            self.logger.debug("Timer dead")

class ManagedTimer:
    __slots__=("_timer", "name", "interval", "func", "_logger")

    _timer: Timer
    name: str
    interval: float
    func: Callable[[], None]

    def __init__(self, func:Callable[[], None], interval=30.5, logger:logging.Logger | None=None) -> None:
        self.func = func
        self.interval = interval
        self.name = ""
        self._timer = Timer(self.interval, self.func)
        self._logger = logger
        self._timer.logger = logger
    
    def reset(self):
        if not self._timer.reset():
            self._timer = Timer(self.interval, self.func)
            self._timer.logger = self._logger
            self._timer.reset()
    
    def cancel(self):
        self._timer.cancel()
