from Tools.Devices.Filters import BaseFilter
import math

class DeltaFilter(BaseFilter):
    _delta = 0.0
    _last_valid_value = 0.0

    def __init__(self, delta=None) -> None:
        super().__init__()
        if delta != None:
            self.set_delta(delta)

    def set_delta(self, delta: float):
        self._delta = delta
    
    def filter(self, new_value:float):
        if math.isnan(new_value):
            return self._last_valid_value
        if math.isnan(self._last_valid_value):
            self._last_valid_value = new_value
            return new_value
        if math.fabs( self._last_valid_value - new_value) >= self._delta:
            self._last_valid_value = new_value
            return new_value
        return self._last_valid_value
