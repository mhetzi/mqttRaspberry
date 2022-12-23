import socket
import schedule

from Mods.CoE.coe_lib.ChannelRegestry import AnalogChannels, DigitalChannels
import bitstring
import logging

class UDP_Sender:

    def __init__(self, channels: AnalogChannels | DigitalChannels, addr: str, port: int, logger:logging.Logger) -> None:
        self._channels = channels
        self._resend_timer = schedule.every(5).minutes.do( self.send_all_channels )
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._addr = addr
        self._port = port
        self._address = (addr, port)
        self._log = logger

    def send_all_channels(self):
        try:
            blist = self._channels.getBytesForAllWrittenPages()
            for b in blist:
                self._sock.sendto(b, self._address)
                cbs = bitstring.ConstBitStream(bytes=b)
                print("Outgoing bytes:")
                cbs.pp()
        except:
            self._log.exception("send_all_channels Exception")
    
    def sendBytes(self, b: bytes):
        cbs = bitstring.ConstBitStream(bytes=b)
        print("Outgoing bytes:")
        cbs.pp()
        self._sock.sendto(b, self._address)

    def stop(self):
        schedule.cancel_job(self._resend_timer)
        self._sock.close()
