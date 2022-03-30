import logging
from Tools.Devices.Filters import BaseFilter
import math
import logging

class DeltaFilter(BaseFilter):
    _delta = 0.0
    _last_valid_value = math.nan

    def __init__(self, delta=None, logger=None) -> None:
        super().__init__()
        self._log = logging.getLogger("Launch") if logger is None else logger.getChild("Delta")
        self._log.setLevel(logging.NOTSET)
        if delta != None:
            self.set_delta(delta)

    def set_delta(self, delta: float):
        self._delta = delta
        self._log.debug("New Delta {} set.".format(delta))
    
    def filter(self, new_value:float):
        if math.isnan(new_value):
            self._log.debug("new_value is NaN")
            return self._last_valid_value
        if math.isnan(self._last_valid_value):
            self._log.debug("last_valid_value is NaN")
            self._last_valid_value = new_value
            return new_value
        if math.fabs( self._last_valid_value - new_value) >= self._delta:
            self._log.debug("{} to {} delta threshold passed. (Delta was: {})".format(self._last_valid_value, new_value, math.fabs( self._last_valid_value - new_value)))
            self._last_valid_value = new_value
            return new_value
        self._log.debug("Received: {}".format(new_value))
        return self._last_valid_value

    def nullOldValues(self):
        self._last_valid_value = 0.0
        return super().nullOldValues()
