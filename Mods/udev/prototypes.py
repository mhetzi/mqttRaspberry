import abc
import pyudev
from Tools.Config import PluginConfig
from Tools.PluginManager import PluginManager

class UdevDeviceProcessor:

    @abc.abstractmethod
    def start(self, context: pyudev.Context): pass

    @abc.abstractmethod
    def stop(self): pass

    @abc.abstractmethod
    def regDevices(self, pm: PluginManager): pass

    @abc.abstractmethod
    def setConfig(self, config: PluginConfig): pass

    @abc.abstractmethod
    def sendUpdate(self): pass