import logging
from Tools.Devices.Filters import BaseFilter
import math
import logging

class TooLowFilter(BaseFilter):
    _min_value = 0.0
    _last_valid_value = math.nan

    def __init__(self, min_value=None, logger=None) -> None:
        super().__init__()
        self.set_min_value(min_value)

    def set_min_value(self, max_val):
        self._min_value = max_val

    def filter(self, new_value):
        self._last_valid_value = new_value if new_value > self._min_value else self._last_valid_value
        return self._last_valid_value

    def nullOldValues(self):
        self._last_valid_value = math.nan
        return super().nullOldValues()