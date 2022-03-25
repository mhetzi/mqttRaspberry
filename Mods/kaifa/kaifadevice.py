import datetime
import logging
import threading
from typing import Union
from Tools.Devices.Filters.RoundingFilter import RoundingFilter

from Tools.Devices.Filters.TooLowFilter import TooLowFilter

try:
    import dlms_cosem.time as dlms_time
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('dlms-cosem', throw=ie, ask=False)
    except err.RestartError:
        import dlms_cosem.time as dlms_time

try:
    from Cryptodome.Cipher import AES
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('pycryptodomex', throw=ie, ask=False)
    except err.RestartError:
        from Cryptodome.Cipher import AES

try:
    import serial
except ImportError as ie:
    try:
        import Tools.error as err
        err.try_install_package('pyserial', throw=ie, ask=False)
    except err.RestartError:
        import serial

import Mods.kaifa.kaifareader as kr

from Tools.Config import PluginConfig
import Tools.Autodiscovery as Discovery
from Tools.Devices import Sensor
from Tools.Devices.Filters import BlockNotChanged, DeltaFilter
from Tools.PluginManager import PluginManager

from Mods.kaifa import kaifatest

class Reader(threading.Thread):

    __slots__ = ("_serial", "_supplier", "_sensors", "_lastStructs", "_register_late", "_devInfo", "kaifaConfig", "_config", "_pm", "_master_log", "_log", "_do_register", "_shutdown", "_serial_errors")

    _serial: serial.Serial
    _supplier: Union[kr.SupplierEVN, kr.SupplierTINETZ]
    _sensors: dict[str, Sensor.Sensor]
    _lastStructs: dict
    _do_register: bool
    _devInfo: Discovery.DeviceInfo
    kaifaConfig: kr.Config
    _pm: PluginManager
    _serial_errors: int

    def __init__(self, subConfig: PluginConfig, logger: logging.Logger) -> None:
        threading.Thread.__init__(self)
        self._config = subConfig
        self._master_log = logger
        self._log = logger
        self._sensors = {}
        self._do_register = False
        self._shutdown = False

        # Create and modify original config object
        self.kaifaConfig = kr.Config(None)
        self.kaifaConfig._config = self._config
        self._serial_errors = 0

    def callback(self, observation: Union[kr.Decrypt, None]):
        if observation is None:
            self._serial_errors += 1
            if self._serial_errors > 15:
                self._serial_errors = 0
                try:
                    self._log.info("Resetting Serial Connection...")
                    self._serial.close()
                except:
                    self._log.exception("Resetting Serial Connection failed!")
            return
        self._serial_errors = 0

        self._log.debug("Processing Kaifa data...")
        structs = kaifatest.getStructs(observation._data_decrypted, self._log)
        self._lastStructs = structs

        for obisID in self._sensors.keys():
            struct = structs[obisID]
            sensor = self._sensors[obisID]
            value, symbol = kaifatest.getValue(struct)
            if symbol == kaifatest.EnumValues.Wh:
                symbol = kaifatest.EnumValues.kWh
                value = value / 1000
            try:
                state = sensor.state(value)
            except:
                self._log.exception("Konnte Kaifa update nicht senden!")

        if self._do_register:
            self._register()
        self._log.debug("Processing Kaifa data done")

    def run(self) -> None:
        self._shutdown = False
        while not self._shutdown:
            try:
                self._master_log.getChild("KR").setLevel(logging.DEBUG)
                _, self._serial, self._supplier = kr.setup(self.kaifaConfig, self._master_log.getChild("KR"))
                self._log.info(f"Serial Port {self._serial.name} erfolgreich geöffnet.")
                kr.mainLoop(self.kaifaConfig, self._log, self._serial, self._supplier, self.callback)
            except serial.PortNotOpenError:
                pass
            except Exception:
                self._log.exception("Kaifa Serial MainLoop")
                import time
                time.sleep(5)
    
    def stop(self):
        self._shutdown = True
        try:
            self._serial.close()
        except:
            pass

    def register(self, pm: PluginManager):
        self._pm = pm
        try:
            if len(self._lastStructs):
                # We allready got a Packet from the Smart Meter, proceed with registering...
                self._log.info("Kaifa data. Proceed with registration...")
                self._register()
                return
        except: pass
        # No valid Packet received, set flag and let callback register
        self._log.info("No Kaifa data. Delaying registration...")
        self._do_register = True
    
    def _register(self):
        # Make New Device for Kaifa Smart Meter
        self._log.debug("Build HA Device info...")
        sys_dev = Discovery.Topics.get_std_devInf()
        self._devInfo = Discovery.DeviceInfo()
        
        meterID = self._lastStructs["id"].decode()

        self._devInfo.via_device = sys_dev.IDs[0]
        self._devInfo.mfr = "Kaifa"
        self._devInfo.IDs = [meterID]

        self._log = self._master_log.getChild(meterID)
        
        if self._config.get("obis_enabled", None) is None:
            self._config["obis_enabled"] = kaifatest.ALL_OBIS_NAMES

        for obis_str in self._config["obis_enabled"]:
            value, symbol = kaifatest.getValue( self._lastStructs[obis_str] )
            if symbol == kaifatest.EnumValues.Wh:
                symbol = kaifatest.EnumValues.kWh
                value = value / 1000
            if obis_str == kaifatest.ObisNames.PowerFactor_str:
                symbol = "%"
                value = value * 100
            
            name = kaifatest.ObisNames.getFriendlyName(obis_str)
            if name is None:
                self._log.warn(f"Obis String {obis_str} is unknown!")
                continue
            
            sensor = Sensor.Sensor(
                self._log,
                self._pm,
                name,
                kaifatest.ObisNames.getDeviceClass(obis_str),
                measurement_unit=symbol.name if isinstance(symbol, kaifatest.EnumValues) else symbol,
                device=self._devInfo,
                nodeID=f"SmartMeter_{meterID}"
            )
            sensor.register()
            if obis_str == kaifatest.ObisNames.ActiveEnergy_out_str:
                sensor.addFilter(TooLowFilter(0.1, self._log))
            sensor.addFilter(DeltaFilter.DeltaFilter(0.0001, self._log))
            sensor.addFilter(RoundingFilter(3, self._log))

            if value > 0:
                sensor.state(value)
            self._sensors[obis_str] = sensor
        self._do_register = False
        self._master_log.getChild("KR").setLevel(logging.INFO)
    
    def resend(self):
        for sens in self._sensors.values():
            sens.resend()