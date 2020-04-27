import asyncio
import click
import logging

from .protocol.exceptions import PacketInvalid
from .protocol.source import Source
from .receive import OpenTTDProtocolReceive
from .send import OpenTTDProtocolSend
from ..helpers.click import click_additional_options

log = logging.getLogger(__name__)


class OpenTTDProtocolTCPContent(asyncio.Protocol, OpenTTDProtocolReceive, OpenTTDProtocolSend):
    proxy_protocol = False

    def __init__(self, callback_class):
        super().__init__()
        self._callback = callback_class
        self._callback.protocol = self
        self._queue = asyncio.Queue()
        self._data = b""
        self.new_connection = True

        self.task = asyncio.create_task(self._process_queue())

    def connection_made(self, transport):
        self.transport = transport
        socket_addr = transport.get_extra_info("peername")
        self.source = Source(self, socket_addr, socket_addr[0], socket_addr[1])

    def connection_lost(self, exc):
        self.task.cancel()

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
                getattr(self._callback, f"receive_{type.name}")(self.source, **kwargs)
            except Exception:
                self.transport.close()
                raise

    def send_packet(self, data):
        self.transport.write(data)


@click_additional_options
@click.option(
    "--proxy-protocol",
    help="Enable Proxy Protocol (v1), and expect all incoming package to have this header.",
    is_flag=True,
)
def click_proxy_protocol(proxy_protocol):
    OpenTTDProtocolTCPContent.proxy_protocol = proxy_protocol
