import logging
from Tools.Devices.Filters import BaseFilter
import math
import logging

class RoundingFilter(BaseFilter):
    _ndigits: int = 0

    def __init__(self, ndigits:int, logger=None) -> None:
        super().__init__()
        self._log = logging.getLogger("Launch") if logger is None else logger.getChild("TooLow")
        self.set_ndigits(ndigits)

    def set_ndigits(self, ndigits:int):
        self._ndigits = ndigits

    def filter(self, new_value):
        return round(number=new_value, ndigits=self._ndigits)

    def nullOldValues(self):
        return super().nullOldValues()