import aiohttp
import asyncio
import click
import logging
import random

from aiohttp import web
from openttd_helpers import click_helper

from .helpers.content_type import get_folder_name_from_content_type
from .helpers.safe_filename import safe_filename

log = logging.getLogger(__name__)
routes = web.RouteTableDef()

RELOAD_SECRET = None
BANANAS_SERVER_APPLICATION = None
CDN_FALLBACK_URL = None
CDN_URL = None
CDN_ACTIVE_URL = []


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
    "--cdn-fallback-url",
    help="Fallback URL in case no --cdn-urls are healthy.",
    show_default=True,
)
@click.option(
    "--cdn-url",
    help="URL of the CDN OpenTTD clients can fetch their HTTP (not HTTPS) downloads.",
    multiple=True,
    show_default=True,
)
def click_web_routes(reload_secret, cdn_fallback_url, cdn_url):
    global RELOAD_SECRET, CDN_FALLBACK_URL, CDN_URL

    RELOAD_SECRET = reload_secret

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
