import asyncio
import click
import logging

from asyncio.coroutines import iscoroutine
from openttd_helpers import click_helper

from .protocol.exceptions import (
    PacketInvalid,
    SocketClosed,
)
from .protocol.source import Source
from .protocol.write import SEND_MTU
from .receive import OpenTTDProtocolReceive
from .send import OpenTTDProtocolSend

log = logging.getLogger(__name__)


class OpenTTDProtocolTCPContent(asyncio.Protocol, OpenTTDProtocolReceive, OpenTTDProtocolSend):
    proxy_protocol = False

    def __init__(self, callback_class):
        super().__init__()
        self._callback = callback_class
        self._queue = asyncio.Queue()
        self._data = b""
        self.new_connection = True

        self.task = asyncio.create_task(self._process_queue())

    def connection_made(self, transport):
        self.transport = transport
        # Have a buffer of several packets, after which we expect it to drain to
        # nearly empty before we start sending again. This reduces the memory
        # this application uses drasticly on slow connections.
        self.transport.set_write_buffer_limits(SEND_MTU * 5, SEND_MTU * 2)

        self._can_write = asyncio.Event()
        self._can_write.set()

        socket_addr = transport.get_extra_info("peername")
        self.source = Source(self, socket_addr, socket_addr[0], socket_addr[1])

    def connection_lost(self, exc):
        self.task.cancel()

    async def _check_closed(self):
        while True:
            # Asyncio doesn't notify us when the connection is closing, only
            # when it is closed. Being in pause-writing means we have stuff
            # in the buffer the client is not receiving. In asyncio language
            # this means the transport is closing, but not closed. As such,
            # we receive no "connection_lost" callback. Force this by resuming
            # write operations, and on the next write it will trigger a
            # SocketClosed exception, which triggers an abort() on the
            # transport, releasing our resources. Yes. It is that complicated.
            await asyncio.sleep(5)
            if self.transport.is_closing():
                self._can_write.set()
                return

    def pause_writing(self):
        self._pause_task = asyncio.create_task(self._check_closed())
        self._can_write.clear()

    def resume_writing(self):
        self._pause_task.cancel()
        self._can_write.set()

    def _detect_source_ip_port(self, data):
        if not self.proxy_protocol:
            return data

        # If enabled, expect new connections to start with PROXY. In this
        # header is the original source of the connection.
        if data[0:5] != b"PROXY":
            log.warning("Receive data without a proxy protocol header from %s:%d", self.source.ip, self.source.port)
            return data

        # This message arrived via the proxy protocol; use the information
        # from this to figure out the real ip and port.
        proxy_end = data.find(b"\r\n")
        proxy = data[0:proxy_end].decode()
        data = data[proxy_end + 2 :]

        # Example how 'proxy' looks:
        #  PROXY TCP4 127.0.0.1 127.0.0.1 33487 12345

        (_, _, ip, _, port, _) = proxy.split(" ")
        self.source = Source(self, self.source.addr, ip, int(port))
        return data

    def data_received(self, data):
        if self.new_connection:
            data = self._detect_source_ip_port(data)
            self.new_connection = False

        self._data = self.receive_data(self._queue, self._data + data)

    async def _process_queue(self):
        while True:
            data = await self._queue.get()

            try:
                type, kwargs = self.receive_packet(self.source, data)
            except PacketInvalid as err:
                log.info("Dropping invalid packet from %s:%d: %r", self.source.ip, self.source.port, err)
                self.transport.close()
                return

            try:
                await getattr(self._callback, f"receive_{type.name}")(self.source, **kwargs)
            except SocketClosed:
                # The other side is closing the connection; it can happen
                # there is still some writes in the buffer, so force a close
                # on our side too to free the resources.
                self.transport.abort()
                return
            except Exception:
                log.exception(f"Internal error: receive_{type.name} triggered an exception")
                self.transport.abort()
                return

    async def send_packet(self, data):
        await self._can_write.wait()

        # When a socket is closed on the other side, and due to the nature of
        # how asyncio is doing writes, we never receive an exception. So,
        # instead, check every time we send something if we are not closed.
        # If we are, inform our caller which should stop transmitting.
        if self.transport.is_closing():
            raise SocketClosed

        res = self.transport.write(data)
        if iscoroutine(res):
            await res


@click_helper.extend
@click.option(
    "--proxy-protocol",
    help="Enable Proxy Protocol (v1), and expect all incoming package to have this header.",
    is_flag=True,
)
def click_proxy_protocol(proxy_protocol):
    OpenTTDProtocolTCPContent.proxy_protocol = proxy_protocol
