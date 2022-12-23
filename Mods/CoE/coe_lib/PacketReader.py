import asyncio
import logging
from . import Message, UDP

class PacketReader:
    udp: UDP.UdpServer
    queue: asyncio.Queue[Message.Message] | None
    looper: asyncio.AbstractEventLoop | None

    def __init__(self, listen_addr: str, listen_port: int, logger: logging.Logger, looper) -> None:
        self.log = logger
        self.udp = UDP.UdpServer(broad_addr=listen_addr, port=listen_port, logger=logger.getChild("UDP"))
        self.udp.name = "TA CoE"
        self.udp.on_message = self._on_message
        self.looper = looper
        self.queue = None if looper is None else asyncio.Queue(4)
    
    def start(self):
        self.udp.start()

    def stop(self):
        self.udp.shutdown()

    def _on_message(self, raw: bytes, sender: tuple):
        m = Message.parseMessage(raw)
        m.ip = sender[0]
        self.on_message(m)
    
    def on_message(self, msg: Message.AnalogMessage | Message.DigitalMessage):
        try:
            asyncio.run_coroutine_threadsafe(self.queue.put(msg), self.looper)
        except asyncio.QueueFull:
            self.log.warning("CoE Message Queue full")


if __name__ == '__main__':
    import sys
    Log_Format = "%(levelname)s %(asctime)s - %(message)s"

    logging.basicConfig(stream = sys.stdout,
                    format = Log_Format, 
                    level = logging.DEBUG)

    logger = logging.getLogger()

    u = None

    async def main():
        logger.debug("in assync main")
        
        logger.info("Start udp server...")
        u = PacketReader(listen_addr="0.0.0.0", listen_port=5441, logger=logger, looper=asyncio.get_running_loop())
        u.start()
        while True:
            msg = await u.queue.get()
            logger.debug(f"Message from {msg.ip} is Digital {msg.isDigital()} or is Analog {msg.isAnalog()}")
            logger.debug(f"Node: {msg.canNode}, Page: {msg.page_nr}, Content: {msg.page_content} ")
    try:
        logger.info("Run async main")
        asyncio.run(main())
    except KeyboardInterrupt:
        if u is not None:
            u.udp.shutdown()