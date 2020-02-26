import click
import git
import logging
import os

from .local import Index as LocalIndex
from ..helpers.click import click_additional_options

log = logging.getLogger(__name__)

_github_url = None


class Index(LocalIndex):
    def __init__(self):
        super().__init__()

        try:
            self._git = git.Repo(self._folder)
        except git.exc.NoSuchPathError:
            self._git = git.Repo.init(self._folder)

        # Make sure the origin is set correctly
        if "origin" not in self._git.remotes:
            self._git.create_remote("origin", _github_url)
        origin = self._git.remotes.origin
        if origin.url != _github_url:
            origin.set_url(_github_url)

    def _fetch_latest(self):
        log.info("Updating index to latest version from GitHub")

        origin = self._git.remotes.origin

        # Checkout the latest master, removing and commits/file changes local
        # might have.
        origin.fetch()
        origin.refs.master.checkout(force=True, B="master")
        for file_name in self._git.untracked_files:
            os.unlink(f"{self._folder}/{file_name}")

    def reload(self, application):
        self._fetch_latest()
        super().reload(application)


@click_additional_options
@click.option(
    "--index-github-url",
    help="Repository URL on GitHub. (index=github only)",
    default="https://github.com/OpenTTD/BaNaNaS",
    show_default=True,
    metavar="URL",
)
def click_index_github(index_github_url):
    global _github_url

    _github_url = index_github_url
