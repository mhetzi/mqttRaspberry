import dataclasses
from io import StringIO
import logging
import sys
from typing import Union
from dataclasses import dataclass
from dataclasses_json import dataclass_json
from dataclasses_json.api import DataClassJsonMixin

import pyudev
from Mods.udev.prototypes import UdevDeviceProcessor
from Tools.Config import PluginConfig
from Tools.Devices import BinarySensor
from Tools.PluginManager import PluginManager

try:
    import pyedid
except ImportError as ie:
    import Tools.error as err
    try:
        err.try_install_package('pyedid', throw=ie, ask=False) # Dont ask, plugin is wanted! So try to get it up and running
    except err.RestartError:
        import pyedid
from pyedid.types.edid import Edid

import os
from pathlib import Path
import hashlib

DRM_PATH = "/sys/class/drm/"

@dataclass
class Display(DataClassJsonMixin):
    mfr:        Union[str, None] = None
    model:      Union[str, None] = None
    madeIn:     int              = 0
    enabled:    bool = False
    connected:  bool = False
    connected_via: Union[str, None] = None
    serial:     int = 0

    product_id: int = 0
    mfr_id:     int = 0
    edid_valid: bool = False
    _saved_hash: int = -1
    
    def __eq__(self, o: object) -> bool:
        return o.__hash__() == self.__hash__()

    def __hash__(self) -> int:
        if self._saved_hash > 0:
            return self._saved_hash

        if None is not self.serial > 0:
            return self.serial
        max_numbers = len(str(sys.maxsize))

        if self.connected:
            sb = f"{self.mfr_id}{self.madeIn}{self.product_id}".encode("ascii")
            hash = hashlib.sha1(sb, usedforsecurity=False).hexdigest()
            return int(f"0x{hash[:max_numbers]}", 0 )
        
        return super().__hash__()

    @staticmethod
    def processEDID(port: Path):
        d = Display()
        with port.joinpath("status").open("r") as f:
            state = f.readline()
            d.connected = "connected" in state
        with port.joinpath("enabled").open("r") as f:
            state = f.readline()
            d.enabled = "enabled" in state
        
        edid = None
        with port.joinpath("edid").open("rb") as f:
            edid_file = b""
            while True:
                buf = f.read(100)
                if not buf:
                    break
                edid_file += buf
            print(edid_file)
            try:
                edid = pyedid.parse_edid(edid_file)
            except:
                pass          
            print(edid)
        if edid is not None:
            d.model = edid.name 
            d.mfr   = edid.manufacturer
            d.madeIn = edid.year
            d.serial = int(edid.serial)
            d.mfr_id = edid.manufacturer_id
            d.product_id = edid.product_id
            d.edid_valid = True
        d._saved_hash = hash(d)
        d.connected_via = port.parts[len(port.parts) - 1]
        return d

class Displays(UdevDeviceProcessor):
    _monitor:  Union[pyudev.Monitor, None] = None
    _observer: Union[pyudev.MonitorObserver, None] = None
    _display_list: dict[int, Display] = {}
    _config: Union[PluginConfig, None] = None

    _sensors: dict[int, BinarySensor.BinarySensor] = {}
    __plugin_manager: Union[PluginManager, None] = None
    
    def __init__(self, log: logging.Logger) -> None:
        super().__init__()
        self._log = log

    def searchMonitors(self) -> list[Display]:
        displays = []
        p = Path(DRM_PATH)
        # search drm cards
        for card in p.iterdir():
            # search Outputs
            if not card.is_dir():
                continue
            for port in card.iterdir():
                try:
                    # extract Display info
                    display = Display.processEDID(port)
                    if display.connected:
                        self._log.info(f"Display {port} wird eingetragen...")
                        displays.append(display)
                except:
                    self._log.error(f"Error Quering Port {port}")
        return displays

    def setConfig(self, config: PluginConfig):
        super().setConfig(config)
        self._config = config
        for display in config.get("displays/list", default=[]):
            d = Display.from_dict(display)
            d.connected = False
            d.connected_via = ""
            self._display_list[hash(d)] = d

    def start(self, context: pyudev.Context):
        super().start(context)
        if self._observer is None or self._observer.is_alive():
            self._monitor = pyudev.Monitor.from_netlink(context=context)
            self._monitor.filter_by("drm")
            self._observer = pyudev.MonitorObserver(self._monitor, self.event)
            self._observer.name = "UdevDRM"
            self._observer.start()
            self._log.info("UDEV Observer started!")

        updated = False
        try:
            r_web = pyedid.Registry.from_web()
            if len(r_web) > 0:
                pyedid.DEFAULT_REGISTRY = r_web
            # Save fresh registry to disk
            if self._config is not None:
                pyedid.DEFAULT_REGISTRY.to_csv(str(self._config.getIndependendPath("EDID_Registry.csv").absolute()))
            updated = True
            self._log.info("EDID Registry aktualisiert")
        except:
            self._log.exception("Error updateing EDID Registry")
        
        if not updated:
            if self._config is not None:
                r_csv = pyedid.Registry.from_csv(str(self._config.getIndependendPath("EDID_Registry.csv").absolute()))
                pyedid.DEFAULT_REGISTRY = r_csv
    
    def event(self, action, device):
        self._log.debug(f"{action = }")
        self._log.debug(f"{device = }")
        self.rescanDevices()
        self.updateDevices()

    def rescanDevices(self):
        current_connected_displays = self.searchMonitors()
        for rdd in self._display_list.values():
            rdd.connected = False
            
        for ccd in current_connected_displays:
            if hash(ccd) not in self._display_list.keys():
                self._log.debug("Erstelle Sensor...")
                self.makeNewDevice(ccd)
            self._display_list[hash(ccd)] = ccd

    def stop(self):
        super().stop()
        if self._observer is not None:
            self._observer.stop()        
    
    def makeNewDevice(self, display: Display):
        if not display.edid_valid:
            self._log.error("EDID is not valid! Ignoring Display...")
            return
        if self._sensors.get(hash(display)) is not None and self.__plugin_manager is None:
            self._log.warn("Device duplicate or pm is none")
            return
        sensor = BinarySensor.BinarySensor(
            self._log,
            self.__plugin_manager,
            f"Monitor_{display.model if display.model is not None else str(display.product_id)}",
            BinarySensor.BinarySensorDeviceClasses.PLUG,
            json_attributes=True,
            value_template="{{ value_json.s }}",
            unique_id=f"sensor.MqttScripts{self.__plugin_manager._client_name}.switch.UDEV.Displays.{hash(display)}"
        )
        sensor.register()
        self._sensors[hash(display)] = sensor

    def updateDevices(self):
        for hsh, dev in self._sensors.items():
            state = {
                "s": 1 if self._display_list.get(hsh, None) is not None and self._display_list[hsh].connected else 0
            }
            if self._display_list.get(hsh, None) is not None:
                state = self._display_list[hsh].to_dict()
                state["s"] = 1 if self._display_list[hsh].connected else 0
            dev.turn(state)
        l = []
        self._log.debug("Speichere Display Liste...")
        for d in self._display_list.values():
            d._saved_hash = hash(d)
            l.append(d.to_dict())
        self._config["displays/list"] = l

    def regDevices(self, pm: PluginManager):
        if self.__plugin_manager is None:
            self.__plugin_manager = pm
        for d in self._display_list.values():
            self.makeNewDevice(d)
        self.updateDevices()
    
    def sendUpdate(self):
        self.rescanDevices()
        self.updateDevices()
        return super().sendUpdate()