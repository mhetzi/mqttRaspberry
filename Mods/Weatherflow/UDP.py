# -*- coding: utf-8 -*-
import socket
import threading
try:
    import json
except ImportError:
    import simplejson as json
import logging

import Mods.Weatherflow.UpdateTypes as ut

class UdpServer(threading.Thread):
    def __init__(self, broad_addr="255.255.255.255", port=50222, logger=logging.getLogger("UdpServer")):
        super().__init__()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((broad_addr, port))
        self.__logger = logger
        self._sock = sock
        self._shutdown = False
        self.setName("Weatherflow UDP Receiver")
        self.on_message = self.__on_message

    def run(self):
        super().run()
        while not self._shutdown:
            data, address = self._sock.recvfrom(2000)
            text = data.decode('utf-8')
            try:
                js = json.loads(text)
                self.on_message(js)
            except KeyboardInterrupt:
                self.__logger.info("Beende CTRL-C bekommen.")
                return
            except:
                if self._shutdown:
                    return
                self.__logger.exception("Message [{}] hat fehler verursacht.".format(text))

    def __on_message(self, msg: dict):
        print("on_message micht implementiert! Nachricht: {}".format(msg))

    def shutdown(self):
        self._shutdown = True
        try:
            self._sock.shutdown(socket.SHUT_RD)
        except:
            pass
        self.join()


if __name__ == '__main__':
    # def print_new_update(msg: dict):
    #     u = ut.parse_json_to_update(msg)
    #     print("Neue Nachricht: {}".format(u))
    #
    # u = UdpServer()
    # u.start()
    # u.on_message = print_new_update
    # try:
    #     u.join()
    # except KeyboardInterrupt:
    #     u.shutdown()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto("""{"serial_number":"AR-00001196" "type":"evt_strike","device_id":1110,"evt":[1493322445,27,3848]}""".encode("utf-8"), ("255.255.255.255", 50222))
