import asyncio
import logging

from .protocol.exceptions import PacketInvalid
from .protocol.source import Source
from .receive import OpenTTDProtocolReceive
from .send import OpenTTDProtocolSend

log = logging.getLogger(__name__)


class OpenTTDProtocolTCPContent(asyncio.Protocol, OpenTTDProtocolReceive, OpenTTDProtocolSend):
    def __init__(self, callback_class):
        super().__init__()
        self._callback = callback_class
        self._callback.protocol = self
        self._queue = asyncio.Queue()
        self._data = b""
        self.is_ipv6 = None

        asyncio.create_task(self._process_queue())

    def connection_made(self, transport):
        self.transport = transport
        socket_addr = transport.get_extra_info("peername")
        self.source = Source(self, socket_addr, socket_addr[0], socket_addr[1])
        # TODO -- Support PROXY protocol

        # In Python, a socket is a tuple of 4 when it is IPv6,
        # and a tuple of 2 if it is IPv4.
        if len(transport.get_extra_info("sockname")) == 4:
            self.is_ipv6 = True
        else:
            self.is_ipv6 = False

    def data_received(self, data):
        self._data = self.receive_data(self._queue, self._data + data)

    async def _process_queue(self):
        while True:
            data = await self._queue.get()

            try:
                type, kwargs = self.receive_packet(self.source, data)
            except PacketInvalid as err:
                log.info("Dropping invalid packet from %r: %r", self.source.addr, err)
                self.transport.close()
                return

            try:
                getattr(self._callback, f"receive_{type.name}")(self.source, **kwargs)
            except Exception:
                self.transport.close()
                raise

    def send_packet(self, data):
        self.transport.write(data)
