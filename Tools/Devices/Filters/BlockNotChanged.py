import logging
from Tools.Devices.Filters import BaseFilter, DontSend, SilentDontSend
import math
import logging

class BlockNotChanged(BaseFilter):
    _last_valid_value = 0.0

    def __init__(self, logger=None) -> None:
        super().__init__()
        self._log = logging.getLogger("Launch") if logger is None else logger.getChild("BlockNotChanged")

    def filter(self, new_value):
        if new_value == self._last_valid_value:
            raise SilentDontSend
        self._last_valid_value = new_value
        return new_value

    def nullOldValues(self):
        self._last_valid_value = 0.0