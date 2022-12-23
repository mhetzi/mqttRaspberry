import socket
import threading
import logging
import sys
import bitstring

class UdpServer(threading.Thread):
    def __init__(self, broad_addr="0.0.0.0", port=5441, logger=logging.getLogger("UdpServer")):
        super().__init__()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((broad_addr, port))
        self.__logger = logger
        self.__logger.info(f"Bound {broad_addr}:{port}")
        self._sock = sock
        self._shutdown = False
        self.name = "UDP Listen"
        self.on_message = self.__on_message

    def run(self):
        super().run()
        while not self._shutdown:
            self.__logger.debug("Recv")
            data, address = self._sock.recvfrom(14)
            self.__logger.debug(f"Packet from {address}")
            bitstring.ConstBitStream(bytes=data).pp()
            try:
                self.on_message(data, address)
            except KeyboardInterrupt:
                self.__logger.info("Beende CTRL-C bekommen.")
                return
            except:
                if self._shutdown:
                    return
                self.__logger.exception("Message [{}] hat fehler verursacht.".format(data))

    def __on_message(self, raw: bytes, sender: tuple):
        print(f"on_message micht implementiert! Nachricht: raw: {raw} )")

    def shutdown(self):
        self._shutdown = True
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except:
            pass
        self.join()


if __name__ == '__main__':
    Log_Format = "%(levelname)s %(asctime)s - %(message)s"

    logging.basicConfig(stream = sys.stdout,
                    format = Log_Format, 
                    level = logging.DEBUG)

    logger = logging.getLogger()
    logger.info("Start udp server...")
    u = UdpServer(logger=logger)
    u.start()
    try:
        u.join()
    except KeyboardInterrupt:
        u.shutdown()