import struct
from . import Datatypes
import bitstring

ANALOG_PAGE_ENTRY = tuple[float, Datatypes.MeasureType]

ANALOG_PAGE_CONTENT = tuple[ANALOG_PAGE_ENTRY,ANALOG_PAGE_ENTRY,ANALOG_PAGE_ENTRY,ANALOG_PAGE_ENTRY]
DIGITA_PAGE_CONTENT = tuple[bool,bool,bool,bool,bool,bool,bool,bool,bool,bool,bool,bool,bool,bool,bool,bool]

class Message:
    __slots__=("__bytes", "canNode", "page_nr", "page_content", "ip")

    ip: str
    canNode: int
    page_nr: int
    page_content: tuple

    def __init__(self, raw: bytes|None) -> None:
        if raw is None:
            return
        self.canNode = raw[0]
        self.page_nr = raw[1]
    
    def isDigital(self):
        return False

    def isAnalog(self):
        return False

class AnalogMessage(Message):
    page_content: ANALOG_PAGE_CONTENT

    def __init__(self, raw: bytes) -> None:
        super().__init__(raw)
        data = struct.unpack_from('<hhhhcccc', raw, 2)
        meastypes = (
            Datatypes.MeasureType.from_bytes(data[4], byteorder='little'),
            Datatypes.MeasureType.from_bytes(data[5], byteorder='little'),
            Datatypes.MeasureType.from_bytes(data[6], byteorder='little'),
            Datatypes.MeasureType.from_bytes(data[7], byteorder='little')
        )
        self.page_content = (
            (data[0] / meastypes[0].getScaleFactor(), meastypes[0]),
            (data[1] / meastypes[1].getScaleFactor(), meastypes[1]),
            (data[2] / meastypes[2].getScaleFactor(), meastypes[2]),
            (data[3] / meastypes[3].getScaleFactor(), meastypes[3])
        )
    
    def isAnalog(self):
        return True


class DigitalMessage(Message):
    page_content: DIGITA_PAGE_CONTENT

    def __init__(self, raw: bytes|None) -> None:
        super().__init__(raw)
        #self.page_content = struct.unpack_from('<????????', raw, 2)
        if raw is None:
            return
        l = []
        for idx in range(2, 4):
            nraw = raw[idx:idx+1]
            bits = bitstring.Bits(bytes=nraw, length=8)
            bits.pp()
            for b in range(7, -1, -1):
                l.append(bits[b])
        
        self.page_content = tuple(l)

    def isDigital(self):
        return True


def parseMessage(data: bytes):
    if data[1] > 0 and data[1] < 9:
        return AnalogMessage(data)
    elif data[1] == 0 or data[1] == 9:
        return DigitalMessage(data)
    else:
        raise Exception("Invalid message received")
    

