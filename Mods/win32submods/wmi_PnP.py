# -*- coding: utf-8 -*-

from Tools.Autodiscovery import BinarySensorDeviceClasses
from time import sleep
from typing import Tuple, Union
from Tools.Config import PluginConfig
from Tools.PluginManager import PluginManager
from Tools.Devices import BinarySensor

from logging import Logger
from threading import Thread

try:
    import wmi
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('wmi', throw=ie, ask=True)
    except err.RestartError:
        import wmi
 
class WMI_PnP:
    _all_services = []
    _pnp_cache: dict[str,dict] = {}
    _pnp_cache_rdy = False
    _shutdown = False
    _registered_devices: dict[str,BinarySensor.BinarySensor] = {}
    _pman: PluginManager = None

    def deviceRemovedThread(self):
        raw_wql = "SELECT * FROM __InstanceDeletionEvent WITHIN 2 WHERE TargetInstance ISA \'Win32_PnPEntity\'" # for removed devices
        c = wmi.WMI ()
        watcher = c.watch_for(raw_wql=raw_wql)
        while not self._pnp_cache_rdy:
            sleep(1)
        self._log.debug("PnP cache ready. Beginne aktives warten auf events")
        while not self._shutdown:
            try:
                pnp = watcher(2500)
                id, entry = self._getPopulatedPnP(pnp)
                if id is None:
                    continue
                if id in self._pnp_cache.keys():
                    self._log.debug("Gerät {} getrennt. sende update...".format(id))
                    self.addDevice(id, entry, False)
                self.sendUpdate(True)
            except wmi.x_wmi_timed_out:
                pass

    def deviceAddedThread(self):
        raw_wql = "SELECT * FROM __InstanceCreationEvent WITHIN 2 WHERE TargetInstance ISA \'Win32_PnPEntity\'" # for added devices
        c = wmi.WMI ()
        watcher = c.watch_for(raw_wql=raw_wql)
        while not self._pnp_cache_rdy:
            sleep(1)
        self._log.debug("PnP cache ready. Beginne aktives warten auf events")
        while not self._shutdown:
            try:
                pnp = watcher(2500)
                self._log.debug("New Device plugged in: {}".format(pnp))
                id, entry = self._getPopulatedPnP(pnp)
                if id is None:
                    continue
                self._log.debug("Device is allowed")
                self.addDevice(id, entry, True)
                self.sendUpdate(True)
            except wmi.x_wmi_timed_out:
                pass
    
    def _getPopulatedPnP(self, pnp) -> Tuple[str, dict]:
        pnp_entry = {}
        service = pnp.wmi_property("Service").value
        if service not in self._all_services:
            self._all_services.append(service)
        
        if service not in self._allowed_services:
            return None, None

        for props in pnp.properties.keys():
            property = pnp.wmi_property(props)
            pnp_entry[property.name] = property.value
        return pnp.id, pnp_entry



    def __init__(self, config: PluginConfig, log: Logger) -> None:
        self._config = PluginConfig(config, "PnP")
        self._allowed_services = self._config.get("allowed", ["monitor"])
        self._log = log.getChild("WMI_PnP")

        self._log.debug("Erstelle Watcher für PnP änderung...")
        self._pnp_added_thread = Thread(name="wmiPnpAdded", target=self.deviceAddedThread)
        self._pnp_added_thread.start()
        self._pnp_removed_thread = Thread(name="wmiPnpRemoved", target=self.deviceRemovedThread)
        self._pnp_removed_thread.start()

        self._log.info("Holen der Geräte informationen...")
        # Get All PnP Devices
        obj = wmi.WMI().Win32_PnPEntity()
        #Filter for Monitors
        for x in obj:
            self._log.debug("Verarbeite {}...".format(x.id))
            id, entry = self._getPopulatedPnP(x)
            if id is not None:
                self.addDevice(id, entry, True)
                self._log.debug("Erlaubtes Gerät hinzugefügt.")
        self._pnp_cache_rdy = True
        self._log.info("Geräte ausgelesen")

    def register(self, wasConnected: bool, pman: PluginManager):
        self._pman = pman
        self.sendUpdate(not wasConnected)

    def addDevice(self, id: str, dev: dict, isConnected=False):
        if not isConnected and id in self._pnp_cache.keys():
            self._pnp_cache.pop(id)
        elif isConnected and id not in self._pnp_cache.keys():
            self._pnp_cache[id] = dev

        if self._pman is not None:
            if id not in self._registered_devices.keys():
                if id not in self._config.get("devices", {}).keys():
                    self._config["devices"][id] = {
                        "Name": dev["Name"],
                        "Service": dev["Service"],
                        "PnPID": id,
                        "DeviceID": dev["DeviceID"]
                    }
                uid = "bsens.win32.wmi.PnP.{}.{}".format(id, dev["Service"])
                sensor = BinarySensor.BinarySensor(
                    self._log, 
                    pman=self._pman,
                    name=dev["Name"],
                    binary_sensor_type=BinarySensorDeviceClasses.PLUG,
                    value_template="{{value_json.pnp_present}}",
                    json_attributes=True,
                    unique_id=uid,
                    subnode_id=dev["DeviceID"]
                )
                self._registered_devices[id] = sensor
                sensor.register()
                self.sendDeviceState(id)
            else:
                sensor = self._registered_devices[id]
                sensor.register()
                self.sendDeviceState(id)

    def sendDeviceState(self, PnPDeviceID: str, forceOff=False):
        dev = self._registered_devices[PnPDeviceID]
        dev_pluggedin = 1 if PnPDeviceID in self._pnp_cache.keys() and not forceOff else 0
        self._log.debug("Gerät {} is da? {}. [{}] Update wird gesendet!".format(PnPDeviceID, dev_pluggedin, self._pnp_cache.keys()))
        js = { }
        js.update(self._config.get("devices", {}).get(PnPDeviceID,{}))
        try:
            js.update(self._pnp_cache.get(PnPDeviceID, None).copy())
        except:
            pass
        js["pnp_present"] = dev_pluggedin
        dev.turn(js)


    def _rebuild_devices(self):
        devices = self._config.get("devices", {})
        for PNPDeviceID in devices.keys():
            self.addDevice(PNPDeviceID, devices[PNPDeviceID], isConnected=PNPDeviceID in self._pnp_cache.keys())
        for PNPDeviceID in self._pnp_cache.keys():
            self.addDevice(PNPDeviceID, self._pnp_cache[PNPDeviceID], isConnected=True)

    def sendUpdate(self, cache_changed=False):
        if cache_changed:
            self._rebuild_devices()
        for PnPDeviceID in self._registered_devices:
            self.sendDeviceState(PnPDeviceID)
    
    def shutdown_watchers(self):
        self._shutdown = True
        self._log.debug("Warte auf added Thread...")
        self._pnp_added_thread.join()
        self._log.debug("Warte auf removed Thread...")
        self._pnp_removed_thread.join()
        self._log.debug("WMI PnP Überwachung beendet")
        for PnPDeviceID in self._registered_devices:
            self.sendDeviceState(PnPDeviceID, True)


        