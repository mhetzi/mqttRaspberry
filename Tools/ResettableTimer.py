# -*- coding: utf-8 -*-
import threading


class ResettableTimer:

    def __init__(self, interval:float, function, userval=None, autorun=True):
        self._userval = userval
        self._func = function
        self._timer = None
        self._interval = interval
        if autorun:
            self.start()

    def _run(self):
        if callable(self._func):
            if self._userval is None:
                self._func()
            else:
                self._func(self._userval)

    def start(self):
        self._timer = threading.Timer(self._interval, self._run)
        self._timer.start()

    def cancel(self):
        self._timer.cancel()

    def reset(self):
        self.cancel()
        self.start()