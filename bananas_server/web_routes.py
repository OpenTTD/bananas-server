import aiohttp
import asyncio
import click
import logging
import random

from aiohttp import web
from openttd_helpers import click_helper
from openttd_protocol.protocol.content import ContentProtocol
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    generate_latest,
    Summary,
)

from .helpers.content_type import get_folder_name_from_content_type
from .helpers.safe_filename import safe_filename

log = logging.getLogger(__name__)
routes = web.RouteTableDef()
stats_download_http_count = Counter("bananas_server_http_download", "Number of HTTP downloads", ["content_type"])
stats_download_http_bytes = Summary(
    "bananas_server_http_download_bytes", "Number of bytes downloaded via HTTP (estimated)", ["content_type"]
)
stats_websocket_count = Counter("bananas_server_websocket", "Number of websocket connections")
stats_websocket_duration = Summary(
    "bananas_server_websocket_duration_seconds", "Duration, in seconds, websockets has been open"
)


RELOAD_SECRET = None
TRUST_FORWARDED_HEADERS = False
BANANAS_SERVER_APPLICATION = None
CDN_FALLBACK_URL = None
CDN_URL = None
CDN_ACTIVE_URL = []


class WebsocketTransport:
    def __init__(self, ws, source):
        self._ws = ws
        self._source = source

    def is_closing(self):
        return False

    async def write(self, data):
        await self._ws.send_bytes(data)

    def abort(self):
        self._ws.do_exit = True

    def close(self):
        self._ws.do_exit = True

    def get_extra_info(self, what):
        if what != "peername":
            raise NotImplementedError("Unknown get_extra_info() request")

        return self._source

    def set_write_buffer_limits(self, hard_limit=None, soft_limit=None):
        pass


async def check_cdn_health():
    await asyncio.sleep(1)

    log.info("Healthchecks for CDN servers %r enabled", CDN_URL)

    # All servers start off as offline
    CDN_ACTIVE_URL[:] = []

    while True:
        active_url = []

        async with aiohttp.ClientSession() as session:
            for cdn_url in CDN_URL:
                try:
                    async with session.get(f"{cdn_url}/healthz") as response:
                        if response.status == 200:
                            active_url.append(cdn_url)
                        else:
                            log.error(f'CDN server "{cdn_url}" failed health check: %d', response.status)
                except Exception as e:
                    log.error(f'CDN server "{cdn_url}" offline: %s', e)

        CDN_ACTIVE_URL[:] = active_url
        await asyncio.sleep(30)


@routes.post("/bananas")
async def balancer_handler(request):
    data = await request.read()

    content_ids = data.decode().strip().split("\n")

    if CDN_ACTIVE_URL:
        cdn_url = random.choice(CDN_ACTIVE_URL)
    else:
        cdn_url = CDN_FALLBACK_URL

    if request.scheme == "https" or (TRUST_FORWARDED_HEADERS and request.headers.get("X-Forwarded-Proto") == "https"):
        cdn_url = cdn_url.replace("http://", "https://")

    response = ""
    for content_id in content_ids:
        try:
            content_id = int(content_id)
        except Exception:
            log.info("Invalid ID '%s' requested; skipping ..", content_id)
            continue

        content_entry = BANANAS_SERVER_APPLICATION.get_by_content_id(content_id)

        # TODO -- Implement trottling for IPs that hit this a lot. These are
        # most likely people scanning all IDs.
        if content_entry is None:
            log.info("Invalid ID '%d' requested; skipping ..", content_id)
            continue

        stats_download_http_count.labels(
            content_type=get_folder_name_from_content_type(content_entry.content_type)
        ).inc()
        stats_download_http_bytes.labels(
            content_type=get_folder_name_from_content_type(content_entry.content_type)
        ).observe(content_entry.filesize)

        folder_name = get_folder_name_from_content_type(content_entry.content_type)
        safe_name = safe_filename(content_entry)
        response += (
            f"{content_id},"
            f"{content_entry.content_type.value},"
            f"{content_entry.filesize},"
            f"{cdn_url}/{folder_name}/{content_entry.unique_id.hex()}/{content_entry.md5sum.hex()}/{safe_name}.tar.gz"
            f"\n"
        )

    return web.HTTPOk(body=response)


async def websocket(request):
    ws = web.WebSocketResponse(protocols=["binary"])
    await ws.prepare(request)

    stats_websocket_count.inc()

    source = request.transport.get_extra_info("peername")

    protocol = ContentProtocol(BANANAS_SERVER_APPLICATION)
    protocol.proxy_protocol = False
    protocol.connection_made(WebsocketTransport(ws, source))

    ws.do_exit = False

    with stats_websocket_duration.time():
        try:
            async for msg in ws:
                # The transport requested that we close down.
                if ws.do_exit:
                    await ws.close()
                    break

                if msg.type == aiohttp.WSMsgType.BINARY:
                    protocol.data_received(msg.data)
                else:
                    # Either unknown protocol or an error; either way, terminate
                    # the connection.
                    await ws.close()
                    break
        except Exception:
            log.exception("WebSocket exception")

        protocol.connection_lost(None)

    return ws


@routes.post("/reload")
async def reload(request):
    if RELOAD_SECRET is None:
        return web.HTTPNotFound()

    data = await request.json()

    if "secret" not in data:
        return web.HTTPNotFound()

    if data["secret"] != RELOAD_SECRET:
        return web.HTTPNotFound()

    await BANANAS_SERVER_APPLICATION.reload()

    return web.HTTPNoContent()


@routes.get("/healthz")
async def healthz_handler(request):
    return web.HTTPOk()


@routes.get("/metrics")
async def metrics_handler(request):
    return web.Response(
        body=generate_latest(),
        headers={
            "Content-Type": CONTENT_TYPE_LATEST,
        },
    )


@routes.get("/")
async def root(request):
    if request.headers.get("Upgrade", "").lower().strip() == "websocket":
        if request.headers.get("Connection", "").lower() == "upgrade":
            await websocket(request)

    return web.HTTPOk(body="")


@routes.route("*", "/{tail:.*}")
async def fallback(request):
    log.warning("Unexpected URL: %s", request.url)
    return web.HTTPNotFound()


@click_helper.extend
@click.option(
    "--reload-secret",
    help="Secret to allow an index reload. Always use this via an environment variable!",
)
@click.option(
    "--trust-forwarded-headers",
    is_flag=True,
    help="Whether to use X-Forwarded-Proto to detect HTTPS sessions. Only use when behind a reverse proxy you trust.",
)
@click.option(
    "--cdn-fallback-url",
    help="Fallback URL in case no --cdn-urls are healthy.",
    show_default=True,
)
@click.option(
    "--cdn-url",
    help="URL of the CDN OpenTTD clients can fetch their HTTP / HTTPS downloads.",
    multiple=True,
    show_default=True,
)
def click_web_routes(reload_secret, trust_forwarded_headers, cdn_fallback_url, cdn_url):
    global RELOAD_SECRET, CDN_FALLBACK_URL, CDN_URL, TRUST_FORWARDED_HEADERS

    RELOAD_SECRET = reload_secret
    TRUST_FORWARDED_HEADERS = trust_forwarded_headers

    cdn_url = list(set(cdn_url))

    # If someone sets only a single cdn-url, don't do healthchecks.
    if len(cdn_url) == 1 and not cdn_fallback_url:
        CDN_FALLBACK_URL = cdn_url[0]
        CDN_URL = []
    elif not cdn_fallback_url:
        raise RuntimeError("Please set --cdn-fallback-url if more than one --cdn-url are given")
    else:
        CDN_FALLBACK_URL = cdn_fallback_url
        CDN_URL = cdn_url

        # Start health checks.
        loop = asyncio.get_event_loop()
        loop.create_task(check_cdn_health())
