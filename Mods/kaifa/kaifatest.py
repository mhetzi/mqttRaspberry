import enum
from typing import Union
from dlms_cosem.cosem import Obis
from dlms_cosem.hdlc import frames
from dlms_cosem.protocol import xdlms
from dlms_cosem.time import datetime_from_bytes
from dlms_cosem.utils import parse_as_dlms_data
from Mods.kaifa.kaifareader import Logger
from Tools.Autodiscovery import DeviceClass, SensorDeviceClasses

# 3-phase
hdlc_data_hex = "0F8006870E0C07E5091B01092F0F00FF88800223090C07E5091B01092F0F00FF888009060100010800FF060000328902020F00161E09060100020800FF060000000002020F00161E09060100010700FF060000000002020F00161B09060100020700FF060000000002020F00161B09060100200700FF12092102020FFF162309060100340700FF12000002020FFF162309060100480700FF12000002020FFF1623090601001F0700FF12000002020FFE162109060100330700FF12000002020FFE162109060100470700FF12000002020FFE1621090601000D0700FF1203E802020FFD16FF090C313831323230303030303039"
data = bytearray(bytes.fromhex(hdlc_data_hex))

class ObisNames:
    ActiveEnergy_in = Obis.from_string("1.0.1.8.0.255")
    ActiveEnergy_out = Obis.from_string("1.0.2.8.0.255")

    RealPower_in = Obis.from_string("1.0.1.7.0.255")
    RealPower_out = Obis.from_string("1.0.2.7.0.255")

    VoltageL1 = Obis.from_string("1.0.32.7.0.255")
    VoltageL2 = Obis.from_string("1.0.52.7.0.255")
    VoltageL3 = Obis.from_string("1.0.72.7.0.255")

    CurrentL1 = Obis.from_string("1.0.31.7.0.255")
    CurrentL2 = Obis.from_string("1.0.51.7.0.255")
    CurrentL3 = Obis.from_string("1.0.71.7.0.255")

    PowerFactor = Obis.from_string("1.0.13.7.0.255")

    ActiveEnergy_in_str  = ActiveEnergy_in.to_string()
    ActiveEnergy_out_str = ActiveEnergy_out.to_string()

    RealPower_in_str  = RealPower_in.to_string()
    RealPower_out_str = RealPower_out.to_string()

    VoltageL1_str = VoltageL1.to_string()
    VoltageL2_str = VoltageL2.to_string()
    VoltageL3_str = VoltageL3.to_string()

    CurrentL1_str =  CurrentL1.to_string()
    CurrentL2_str =  CurrentL2.to_string()
    CurrentL3_str =  CurrentL3.to_string()

    PowerFactor_str = PowerFactor.to_string()

    @staticmethod
    def getFriendlyName(obis: Union[str, Obis]):
        if isinstance(obis, Obis):
            obis = obis.to_string()
        match obis:
            case ObisNames.ActiveEnergy_in_str:
                return "Wirkenergie +"
            case ObisNames.ActiveEnergy_out_str:
                return "Wirkenergie -"
            case ObisNames.RealPower_in_str:
                return "Momentanleistung +"
            case ObisNames.RealPower_out_str:
                return "Momentanleistung -"
            case ObisNames.VoltageL1_str:
                return "Spannung L1"
            case ObisNames.VoltageL2_str:
                return "Spannung L2"
            case ObisNames.VoltageL3_str:
                return "Spannung L3"
            case ObisNames.CurrentL1_str:
                return "Strom L1"
            case ObisNames.CurrentL2_str:
                return "Strom L2"
            case ObisNames.CurrentL3_str:
                return "Strom L3"
            case ObisNames.PowerFactor_str:
                return "Leistungsfaktor"
            case _:
                return None
    @staticmethod
    def getDeviceClass(obis: Union[str, Obis]):
        if isinstance(obis, Obis):
            obis = obis.to_string()
        match obis:
            case (ObisNames.ActiveEnergy_in_str | ObisNames.ActiveEnergy_out_str):
                return SensorDeviceClasses.ENERGY
            case (ObisNames.RealPower_in_str | ObisNames.RealPower_out_str):
                return SensorDeviceClasses.POWER
            case (ObisNames.VoltageL1_str | ObisNames.VoltageL2_str | ObisNames.VoltageL3_str):
                return SensorDeviceClasses.VOLTAGE
            case (ObisNames.CurrentL1_str | ObisNames.CurrentL2_str | ObisNames.CurrentL3_str):
                return SensorDeviceClasses.CURRENT
            case ObisNames.PowerFactor_str:
                return SensorDeviceClasses.POWER_FACTOR
            case _:
                return SensorDeviceClasses.GENERIC_SENSOR

            

ALL_OBIS_NAMES = [
    ObisNames.ActiveEnergy_in.to_string(),
    ObisNames.ActiveEnergy_out.to_string(),
    ObisNames.RealPower_in.to_string(),
    ObisNames.RealPower_out.to_string(),
    ObisNames.VoltageL1.to_string(),
    ObisNames.VoltageL2.to_string(),
    ObisNames.VoltageL3.to_string(),
    ObisNames.CurrentL1.to_string(),
    ObisNames.CurrentL2.to_string(),
    ObisNames.CurrentL3.to_string(),
    ObisNames.PowerFactor.to_string()
    ]

class EnumValues(enum.IntEnum):
    Wh = 0x1E
    kWh = 0x1D
    W  = 0x1B
    V  = 0x23
    A  = 0x21
    Unknown = 0xFF

def getValue(struct: tuple):
    scale = struct[1][0]
    #scale = scale - 256 if scale > 128 else scale
    return struct[0] if scale == 0 else struct[0] * (10 ** scale), EnumValues(struct[1][1])

def getStructs(data: bytes, logger=None):
    dn = xdlms.DataNotification.from_bytes(data)  # The first 3 bytes should be ignored.
    result = parse_as_dlms_data(dn.body)

    # First is date
    date_row = result.pop(0)
    #clock_obis = Obis.from_bytes(date_row)
    clock, stats = datetime_from_bytes(date_row)
    if logger is not None:
        logger.debug(f"Clock object: datetime={clock}")
    else:
        print(f"Clock object: datetime={clock}")

    offset = 0

    structs = {"system": (clock, stats)}

    while offset < len(result):
        try:
            structs[Obis.from_bytes(result[offset]).to_string()] = ( result[offset+1:offset+3] )
            offset += 3
        except ValueError:
            structs["id"] = result[offset]
            offset += 1
    return structs

if __name__ == "__main__":
    print(data[0])
    dn = xdlms.DataNotification.from_bytes(bytes.fromhex(hdlc_data_hex))  # The first 3 bytes should be ignored.
    result = parse_as_dlms_data(dn.body)

    # First is date
    date_row = result.pop(0)
    #clock_obis = Obis.from_bytes(date_row)
    clock, stats = datetime_from_bytes(date_row)
    print(f"Clock object: datetime={clock}")

    offset = 0

    structs = {}

    while offset < len(result):
        try:
            structs[Obis.from_bytes(result[offset]).to_string()] = ( result[offset+1:offset+3] )
            offset += 3
        except ValueError:
            structs["id"] = result[offset]
            offset += 1
    
    print(structs)

    print(getValue(structs[ObisNames.ActiveEnergy_in.to_string()]))

    # rest is data
    #for item in result:
    #    try:
    #        obis = Obis.from_bytes(item)
    #        value = item[1]
    #        print(f"{obis.to_string()}={value}")
    #    except ValueError:
    #        print(f"{item = } kann nich als  Obis geparst werden!")
