import asyncio
import click
import logging

from aiohttp import web
from aiohttp.web_log import AccessLogger

from . import web_routes
from .application.bananas_server import Application
from .helpers.click import (
    click_additional_options,
    import_module,
)
from .helpers.sentry import click_sentry
from .index.github import click_index_github
from .index.local import click_index_local
from .storage.local import click_storage_local
from .storage.s3 import click_storage_s3
from .openttd import tcp_content
from .openttd.tcp_content import click_proxy_protocol

log = logging.getLogger(__name__)

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


class ErrorOnlyAccessLogger(AccessLogger):
    def log(self, request, response, time):
        # Only log if the status was not successful
        if not (200 <= response.status < 400):
            super().log(request, response, time)


async def run_server(application, bind, port):
    loop = asyncio.get_event_loop()

    server = await loop.create_server(
        lambda: tcp_content.OpenTTDProtocolTCPContent(application),
        host=bind,
        port=port,
        reuse_port=True,
        start_serving=True,
    )
    log.info(f"Listening on {bind}:{port} ...")

    return server


@click_additional_options
def click_logging():
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S", level=logging.INFO
    )


@click.command(context_settings=CONTEXT_SETTINGS)
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
    callback=import_module("bananas_server.storage", "Storage"),
)
@click_storage_local
@click_storage_s3
@click.option(
    "--index",
    type=click.Choice(["local", "github"], case_sensitive=False),
    required=True,
    callback=import_module("bananas_server.index", "Index"),
)
@click_index_local
@click_index_github
@web_routes.click_web_routes
@click.option("--validate", help="Only validate BaNaNaS files and exit", is_flag=True)
@click_proxy_protocol
def main(bind, content_port, web_port, storage, index, validate):
    app_instance = Application(storage(), index())

    if validate:
        return

    loop = asyncio.get_event_loop()
    server = loop.run_until_complete(run_server(app_instance, bind, content_port))

    web_routes.BANANAS_SERVER_APPLICATION = app_instance

    webapp = web.Application()
    webapp.add_routes(web_routes.routes)

    web.run_app(webapp, host=bind, port=web_port, access_log_class=ErrorOnlyAccessLogger)

    log.info(f"Shutting down bananas_server ...")
    server.close()


if __name__ == "__main__":
    main(auto_envvar_prefix="BANANAS_SERVER")
