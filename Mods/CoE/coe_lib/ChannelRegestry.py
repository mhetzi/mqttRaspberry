from . import Message
from .Datatypes import MeasureType
import bitstring

ANALOG_CHANNEL_TYPE = tuple[int, int, float, MeasureType]
DIGITAL_CHANNEL_TYPE = tuple[int, int, bool]

class CanNode:
    __slots__ = ("pages", "node")

    pages: dict[int, list | tuple]
    node: int

    def __init__(self, node: int) -> None:
        self.node = node
        self.pages = {}
        self.pages[0] = []
        self.pages[9] = []
        for i in range(0 ,16):
            self.pages[0].append(False)
        for i in range(0 ,16):
            self.pages[9].append(False)
        
        for i in range(1,9):
            self.pages[i] = (0,0,0,0, MeasureType.NONE,MeasureType.NONE,MeasureType.NONE,MeasureType.NONE)
    
    def updatePageEntry(self, page: int, page_index: int, val: bool | tuple[float, MeasureType]):
        if (page == 0 or page == 9) and isinstance(val, bool):
            self.pages[page][page_index] = val
        elif (page > 0 and page < 9) and isinstance(val, tuple):
            pip = page_index + 1
            cpv = list(self.pages[page][:4])
            cpt = list(self.pages[page][4:])
            cpv[page_index] = val[0]
            cpt[page_index] = val[1]
            self.pages[page] = tuple(cpv+cpt)
    
    def getBytesForPage(self, page:int) -> bytes:
        barr = bitstring.BitArray()
        barr.append(self.node.to_bytes(1, "big"))
        barr.append(page.to_bytes(1, "big"))
        if page == 0 or page == 9:
            byteS = (self.pages[page][:8], self.pages[page][8:])
            for byte in byteS:
                s = "0b"
                for bit in range(7, -1, -1):
                    s += str(1 if byte[bit] else 0)
                barr.append(s)
            for _ in range(0, 11):
                barr.append(int(0).to_bytes(1, byteorder="little"))
        elif page > 0 and page < 9:
            vals: tuple[float, float,float, float] = self.pages[page][:4]
            types: tuple[MeasureType, MeasureType,MeasureType, MeasureType] = self.pages[page][4:]
            
            for v in range(0, 5):
                barr.append(int(vals[v] * types[v].getScaleFactor()))
            for v in range(0, 5):
                barr.append(types[v].to_bytes(1, "little"))

        return barr.bytes

class CanNodeReg:
    __slots__ = ("nodes")

    nodes: dict[int, CanNode]

    def __init__(self) -> None:
        self.nodes = {}

    def submitMessage(self, msg: Message.DigitalMessage | Message.AnalogMessage):
        pass
    
    def getPageEntry(self, node: int, page: int) -> bytes:
        if self.nodes.get(node, None) is None:
            raise AttributeError("Node not in list!")
        return self.nodes[node].getBytesForPage(page)

    def updateDigitalPageEntry(self, node: int, page: int, pageIndex: int, val: bool) -> bytes:
        if self.nodes.get(node, None) is None:
            self.nodes[node] = CanNode(node)
            self.nodes[node].node = node

        self.nodes[node].updatePageEntry(page, pageIndex, val)
        return self.nodes[node].getBytesForPage(page)

    def updateAnalogPageEntry(self, node: int, page: int, pageIndex: int, val: float, t: MeasureType) -> bytes:
        if self.nodes.get(node, None) is None:
            self.nodes[node] = CanNode(node)
            self.nodes[node].node = node

        self.nodes[node].updatePageEntry(page, pageIndex, (val, t))
        return self.nodes[node].getBytesForPage(page)

class AnalogChannels:
    __slots__ = ("channels", "_nodes", "_dirty_pages", "on_changed_value")

    channels: dict[str, ANALOG_CHANNEL_TYPE]
    _nodes: CanNodeReg | None
    _dirty_pages: dict[int, list[int]] # [node, list[page]]

    def __init__(self, nodes: CanNodeReg | None) -> None:
        self._nodes = nodes
        self.channels = {}
        self._dirty_pages = {}
        self.on_changed_value = self._on_changed_value

    def getChannelData(self, node: int, channel: int) -> ANALOG_CHANNEL_TYPE:
        ids = self.getChannelID(node, channel)
        return self.channels.get(ids, (-1,-1, -9999, MeasureType.NONE))
    
    def getChannelID(self, node: int, channel: int):
        return f"A_{node}_{channel}"
    
    def submitMessage(self, msg: Message.AnalogMessage):
        node = msg.canNode
        for idx in range(0,3):
            channel = msg.page_nr + idx - 1
            ids = self.getChannelID(node, channel)
            data: ANALOG_CHANNEL_TYPE = (
                node, channel, msg.page_content[idx][0], msg.page_content[idx][1]
            )
            old_data= self.channels.get(ids, None)
            self.channels[ids] = data

            if old_data is None or old_data[2] != data[2]:
                self.on_changed_value(msg.ip, data)

    def _on_changed_value(self, addr: str, channel: ANALOG_CHANNEL_TYPE):
        raise NotImplementedError()

    def setChannel(self, node: int, channel: int, val: float, type: MeasureType) -> bytes:
        channel = channel
        ids = self.getChannelID(node, channel)
        self.channels[ids] = (node, channel, val, type)
        page = int(channel / 4)
        page_idx = int(channel % 4)

        if self._dirty_pages.get(node, None) is None:
            self._dirty_pages[node] = [page]
        if page not in self._dirty_pages[node]:
            self._dirty_pages[node].append(page)

        return self._nodes.updateAnalogPageEntry(node, page, page_idx, val, type)
    
    def getBytesForAllWrittenPages(self) -> list[bytes]:
        l: list[bytes] = []
        for node, page_list in self._dirty_pages.items():
            for page in page_list:
                l.append( self._nodes.getPageEntry(node, page) )
        for _ in range(0, 11):
            l.append(bytes(0))
        return l


class DigitalChannels:
    __slots__ = ("channels", "_nodes", "_dirty_pages", "on_changed_value")

    channels: dict[str, DIGITAL_CHANNEL_TYPE]
    _nodes: CanNodeReg | None
    _dirty_pages: dict[int, list[int]] # [node, list[page]]

    def __init__(self, nodes: CanNodeReg | None, callback=None) -> None:
        self._nodes = nodes
        self.channels = {}
        self._dirty_pages = {}
        self.on_changed_value = self._on_changed_value

    def getChannelData(self, node: int, channel: int) -> DIGITAL_CHANNEL_TYPE:
        ids = self.getChannelID(node, channel)
        return self.channels.get(ids, (-1,-1, False))

    def getChannelID(self, node: int, channel: int):
        return f"D_{node}_{channel}"
    
    def submitMessage(self, msg: Message.DigitalMessage):
        node = msg.canNode
        for idx in range(0,15):
            channel = msg.page_nr + idx
            ids = self.getChannelID(node, channel)
            data: DIGITAL_CHANNEL_TYPE = (
                node, channel, msg.page_content[idx]
            )
            old_data= self.channels.get(ids, None)
            self.channels[ids] = data

            if old_data is None or old_data[2] != data[2]:
                self.on_changed_value(msg.ip, data)
    
    def setChannel(self, node: int, channel: int, b: bool) -> bytes:
        channel = channel
        ids = self.getChannelID(node, channel)
        self.channels[ids] = (node, channel, b)
        page = 0 if channel < 16 else 9

        if self._dirty_pages.get(node, None) is None:
            self._dirty_pages[node] = [page]
        if page not in self._dirty_pages[node]:
            self._dirty_pages[node].append(page)

        return self._nodes.updateDigitalPageEntry(node, page, channel - 15 if page == 9 else channel, b)
    
    def getBytesForAllWrittenPages(self) -> list[bytes]:
        l: list[bytes] = []
        for node, page_list in self._dirty_pages.items():
            for page in page_list:
                l.append( self._nodes.getPageEntry(node, page) )
        return l

    def _on_changed_value(self, addr: str, channel: DIGITAL_CHANNEL_TYPE):
        raise NotImplementedError()