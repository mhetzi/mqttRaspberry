# -*- coding: utf-8 -*-

from abc import abstractmethod
from typing import Union

class WindowEventReciever:
    def __init__(self, window_event_processor) -> None:
        self._wep = window_event_processor

    @abstractmethod
    def on_window_event(self, hwnd, msg, wparam, lparam) -> Union[None, bool]:
        pass

    @abstractmethod
    def register(self, wasConnected):
        pass

    @abstractmethod
    def sendUpdate(self, force=True):
        pass

    @abstractmethod
    def shutdown(self):
        pass