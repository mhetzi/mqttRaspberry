from typing import Union
import paho.mqtt.client as mclient
import logging

import  Tools.Config as conf
from    Tools.PluginManager import PluginManager, PluginInterface
from    Tools.Devices.Sensor import Sensor, SensorDeviceClasses

try:
    import pyudev
except ImportError as ie:
    import Tools.error as err
    try:
        err.try_install_package('pyudev', throw=ie, ask=False) # Dont ask, plugin is wanted! So try to get it up and running
    except err.RestartError:
        import pyudev

import Mods.udev.prototypes as udevp

class UdevPlugin(PluginInterface):
    _plugin_manager: Union[PluginManager, None] = None
    _sub_plugins: list[udevp.UdevDeviceProcessor] = []

    def __init__(self, client: mclient.Client, opts: conf.PluginConfig, logger: logging.Logger, device_id: str):
        self._config = opts
        self.__client = client
        self.__logger = logger.getChild("udev")

        self._context = pyudev.Context()

        if opts["displays/enabled"]:
            import Mods.udev.Display as d
            dp = d.Displays(self.__logger)
            dp.setConfig(self._config)
            self._sub_plugins.append(dp)

    def set_pluginManager(self, pm: PluginManager):
        self._plugin_manager = pm

    def register(self, wasConnected=False):
        super().register(wasConnected=wasConnected)
        for sp in self._sub_plugins:
            if self._plugin_manager is not None:
                sp.regDevices(self._plugin_manager)
                if not wasConnected:
                    sp.start(self._context)

    def stop(self):
        self.__logger.debug("Weitergabe von stop()...")
        for sp in self._sub_plugins:
            sp.stop()

    def sendStates(self):
        self.send_update(True)

    def send_update(self, force=False):
        for sp in self._sub_plugins:
            sp.sendUpdate()