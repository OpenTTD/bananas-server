import asyncio
import click
import logging

from aiohttp import web
from aiohttp.web_log import AccessLogger
from openttd_helpers import click_helper
from openttd_helpers.logging_helper import click_logging
from openttd_helpers.sentry_helper import click_sentry
from openttd_protocol.protocol.content import ContentProtocol
from prometheus_client import (
    Info,
    metrics,
)

from . import web_routes
from .application.bananas_server import Application
from .index.github import click_index_github
from .index.local import click_index_local
from .storage.local import click_storage_local
from .storage.s3 import click_storage_s3

log = logging.getLogger(__name__)

# The name of the header to use for remote IP addresses.
REMOTE_IP_HEADER = None

# Disable the "_created" metrics, as they are not useful.
metrics._use_created = False


class ErrorOnlyAccessLogger(AccessLogger):
    def log(self, request, response, time):
        # Only log if the status was not successful
        if not (200 <= response.status < 400):
            if REMOTE_IP_HEADER and REMOTE_IP_HEADER in request.headers:
                request = request.clone(remote=request.headers[REMOTE_IP_HEADER])
            super().log(request, response, time)


@web.middleware
async def remote_ip_header_middleware(request, handler):
    if REMOTE_IP_HEADER in request.headers:
        request = request.clone(remote=request.headers[REMOTE_IP_HEADER])
    return await handler(request)


async def run_server(application, bind, port):
    loop = asyncio.get_event_loop()

    server = await loop.create_server(
        lambda: ContentProtocol(application),
        host=bind,
        port=port,
        reuse_port=True,
        start_serving=True,
    )
    log.info(f"Listening on {bind}:{port} ...")

    return server


@click_helper.command()
@click_logging  # Should always be on top, as it initializes the logging
@click_sentry
@click.option(
    "--bind", help="The IP to bind the server to", multiple=True, default=["::1", "127.0.0.1"], show_default=True
)
@click.option("--content-port", help="Port of the content server", default=3978, show_default=True)
@click.option("--web-port", help="Port of the web server", default=80, show_default=True)
@click.option(
    "--storage",
    type=click.Choice(["local", "s3"], case_sensitive=False),
    required=True,
    callback=click_helper.import_module("bananas_server.storage", "Storage"),
)
@click_storage_local
@click_storage_s3
@click.option(
    "--index",
    type=click.Choice(["local", "github"], case_sensitive=False),
    required=True,
    callback=click_helper.import_module("bananas_server.index", "Index"),
)
@click_index_local
@click_index_github
@web_routes.click_web_routes
@click.option(
    "--bootstrap-unique-id",
    help="Unique-id of the content entry to use as Base Graphic during OpenTTD client's bootstrap",
)
@click.option(
    "--remote-ip-header",
    help="Header which contains the remote IP address. Make sure you trust this header!",
)
@click.option("--validate", help="Only validate BaNaNaS files and exit", is_flag=True)
@click.option(
    "--proxy-protocol",
    help="Enable Proxy Protocol (v1), and expect all incoming streams to have this header "
    "(HINT: for nginx, configure proxy_requests to 1).",
    is_flag=True,
)
def main(bind, content_port, web_port, storage, index, bootstrap_unique_id, remote_ip_header, validate, proxy_protocol):
    with open(".version") as f:
        release = f.readline().strip()
    Info("bananas_server", "BaNaNaS Server").info({"version": release})

    app_instance = Application(storage(), index(), bootstrap_unique_id)

    if validate:
        return

    loop = asyncio.new_event_loop()
    server = loop.run_until_complete(run_server(app_instance, bind, content_port))

    ContentProtocol.proxy_protocol = proxy_protocol

    web_routes.BANANAS_SERVER_APPLICATION = app_instance

    webapp = web.Application()
    if remote_ip_header:
        global REMOTE_IP_HEADER
        REMOTE_IP_HEADER = remote_ip_header.upper()
        webapp.middlewares.insert(0, remote_ip_header_middleware)

    webapp.add_routes(web_routes.routes)

    web.run_app(webapp, host=bind, port=web_port, access_log_class=ErrorOnlyAccessLogger, loop=loop)

    log.info("Shutting down bananas_server ...")
    server.close()


if __name__ == "__main__":
    main(auto_envvar_prefix="BANANAS_SERVER")
