import logging
from Tools.Devices.Filters import BaseFilter
import math
import logging
from time import perf_counter

class MinTimeElapsedFilter(BaseFilter):
    _min_elapsed = 0.0
    _last_valid_value = 0.0
    _start = 0

    def __init__(self, min_elapsed_seconds=None, logger=None) -> None:
        super().__init__()
        self._log = logging.getLogger("Launch") if logger is None else logger.getChild("MinTimeElapsedFilter")
        if min_elapsed_seconds != None:
            self.set_min_elapsed_seconds(min_elapsed_seconds)

    def set_min_elapsed_seconds(self, _min_elapsed: float):
        self._min_elapsed = _min_elapsed
        self._log.debug("New MinElapsedTime {} set.".format(_min_elapsed))
    
    def filter(self, new_value):
        self._log.debug("Received: {}".format(new_value))
        current_time = perf_counter()
        if (current_time - self._start) > self._min_elapsed:
            self._last_valid_value = new_value
            self._start = current_time
        return self._last_valid_value

    def nullOldValues(self):
        self._last_valid_value = 0.0
        return super().nullOldValues()
