import click
import logging

from aiohttp import web

from .helpers.click import click_additional_options
from .helpers.content_type import get_folder_name_from_content_type
from .helpers.safe_filename import safe_filename

log = logging.getLogger(__name__)
routes = web.RouteTableDef()

RELOAD_SECRET = None
BANANAS_SERVER_APPLICATION = None
CDN_URL = None


@routes.post("/bananas")
async def balancer_handler(request):
    data = await request.read()

    content_ids = data.decode().strip().split("\n")

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
            f"{CDN_URL}/{folder_name}/{content_entry.unique_id.hex()}/{content_entry.md5sum.hex()}/{safe_name}.tar.gz"
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


@click_additional_options
@click.option(
    "--reload-secret", help="Secret to allow an index reload. Always use this via an environment variable!",
)
@click.option(
    "--cdn-url",
    help="URL of the CDN OpenTTD clients can fetch their HTTP (not HTTPS) downloads.",
    default="http://client-cdn.openttd.org",
    show_default=True,
)
def click_web_routes(reload_secret, cdn_url):
    global RELOAD_SECRET, CDN_URL

    RELOAD_SECRET = reload_secret
    CDN_URL = cdn_url
