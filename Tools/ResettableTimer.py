# -*- coding: utf-8 -*-
import threading
import schedule

class ResettableTimer:

    def __init__(self, interval:float, function, userval=None, autorun=True):
        self._userval = userval
        self._func = function
        self._interval = interval
        self._shed_task = None
        if autorun:
            self.start()

    def _run(self):
        if callable(self._func):
            if self._userval is None:
                self._func()
            else:
                self._func(self._userval)
    
    def _bootstrap(self):
        try:
            self._run()
        except:
            pass
        self.cancel()

    def start(self):
        self._shed_task = schedule.every(interval=self._interval).seconds
        self._shed_task.do(self._bootstrap)

    def cancel(self):
        if self._shed_task is not None:
            schedule.cancel_job(self._shed_task)

    def reset(self):
        self.cancel()
        self.start()

    def countdown(self):
        if self._shed_task is None:
            self.start()