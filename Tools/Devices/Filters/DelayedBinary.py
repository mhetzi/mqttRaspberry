import logging
from Tools.Devices.Filters import BaseFilter, DontSend, SilentDontSend
from Tools.ResettableTimer import ResettableTimer
from Tools.Devices.BinarySensor import BinarySensor

class DelayedBinary(BaseFilter):
    _last_valid_value = 0.0

    def __init__(self, logger=None, interval=1, delayOn=False, delayOff=False, sensor:BinarySensor | None=None) -> None:
        super().__init__()
        self._delayOn = delayOn
        self._delayOff = delayOff
        self._log = logging.getLogger("Launch") if logger is None else logger.getChild("DelayedOff")
        self._timer = ResettableTimer(interval=interval, function=lambda n: self.delaySuccess(), autorun=False)

    def delaySuccess(self):
        pass

    def filter(self, new_value:bool):
        if new_value and self._delayOn:
            raise SilentDontSend
        self._last_valid_value = new_value
        return new_value

    def nullOldValues(self):
        self._last_valid_value = 0.0