from paho.mqtt.client import Client as MqttClient
import logging

from Tools.Config import BasicConfig, PluginConfig
from Tools import PluginManager

import dasbus
from dasbus.connection import SystemMessageBus

class NetworkManagerDevice:
    def __init__(self, device_path: str) -> None:
        pass

    def stop(self):
        pass

class NetworkManagerPlugin(PluginManager.PluginInterface):
    _dbus_system: SystemMessageBus
    _nm_devices: dict[str, NetworkManagerDevice] = {}

    def __init__(self, client: MqttClient, opts: BasicConfig, logger: logging.Logger, device_id: str):
        import NetworkManager
        self._config = PluginConfig(opts, NetworkManager.PluginLoader.getConfigKey())
        self._logger = logger.getChild(NetworkManager.PluginLoader.getConfigKey())
        self._client = client
        self._device_id = device_id

        self._dbus_system = SystemMessageBus()
        self._proxy  = self._dbus_system.get_proxy('org.freedesktop.NetworkManager', '/org/freedesktop/NetworkManager')
        self._dev_added_notify  = self._proxy.DeviceAdded.connect(   lambda path: self.mod_devices(is_new=True,  path=path) )
        self._dev_rem_notify    = self._proxy.DeviceRemoved.connect( lambda path: self.mod_devices(is_new=False, path=path) )
    
    def mod_devices(self, path, is_new=True):
        if not is_new and path in self._nm_devices.keys():
            self._nm_devices[path].stop()
            del self._nm_devices[path]
        elif is_new:
            self._logger.debug(f"{path=}: Creating Device...")
            self._nm_devices[path] = NetworkManagerDevice(path)

    def set_pluginManager(self, pm:PluginManager.PluginManager):
        self._pluginManager = pm

    def register(self, newClient: MqttClient, wasConnected=False):
        self._client = newClient
        if not wasConnected:
            for d in self._proxy.GetAllDevices():
                self._logger.debug(f"{d=}: Creating Device...")
                self._nm_devices[d] = NetworkManagerDevice(d)

    def stop(self):
        for d in self._nm_devices.values():
            d.stop()

    def sendStates(self):
        pass