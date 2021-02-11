import logging
from Tools.Devices.Filters import BaseFilter
import math
import logging

class TooHighFilter(BaseFilter):
    _max_value = 0.0
    _last_valid_value = 0.0

    def __init__(self, max_value=None, logger=None) -> None:
        super().__init__()
        self._log = logging.getLogger("Launch") if logger is None else logger.getChild("TooHigh")
        self.set_max_value(max_value)

    def set_max_value(self, max_val):
        self._max_value = max_val

    def filter(self, new_value):
        self._last_valid_value = new_value if new_value < self._max_value else self._last_valid_value
        return self._last_valid_value

    def nullOldValues(self):
        return super().nullOldValues()