class BaseFilter:
    def filter(self, new_value):
        pass

    def nullOldValues(self):
        pass

class DontSend(Exception):
    pass

class SilentDontSend(DontSend):
    pass