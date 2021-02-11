import logging
from Tools.Devices.Filters import BaseFilter
import math
import logging

class RangedFilter(BaseFilter):
    _range = 0.0
    _last_valid_value = 0.0
    _insane = 0
    _max_insane = 0

    def __init__(self, range, max_insane, logger=None) -> None:
        super().__init__()
        self._log = logging.getLogger("Launch") if logger is None else logger.getChild("RangedFilter")
        self.set_range(range, max_insane)

    def set_range(self, range, minsane):
        self._range = range
        self._max_insane = minsane

    def filter(self, new_value):
        abs = math.fabs(new_value - self._last_valid_value)
        if abs >= self._range and self._insane >= self._max_insane:
            self._last_valid_value = new_value
            self._insane = 0
            return new_value
        if abs >= self._range and self._insane:
            self._insane += 1
            return self._last_valid_value
        self._last_valid_value = new_value
        self._insane = 0
        return new_value

    def nullOldValues(self):
        self._last_valid_value = 0
        self._insane = 0