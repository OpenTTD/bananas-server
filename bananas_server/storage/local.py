import click
import os

from ..helpers.click import click_additional_options
from ..helpers.content_type import get_folder_name_from_content_type

_folder = None


class Stream:
    def __init__(self, filename, filesize):
        self.fp = open(filename, "rb")
        self.filesize = filesize

    def read(self, count):
        data = self.fp.read(count)
        self.filesize -= len(data)
        return data

    def eof(self):
        return self.filesize == 0


class Storage:
    def __init__(self):
        self.folder = _folder

    def _get_filename(self, content_entry):
        content_type_folder_name = get_folder_name_from_content_type(content_entry.content_type)
        unique_id = content_entry.unique_id.hex()
        md5sum = content_entry.md5sum.hex()

        return f"{self.folder}/{content_type_folder_name}/{unique_id}/{md5sum}.tar.gz"

    def clear_cache(self):
        pass

    def list_folder(self, content_type, unique_id=None):
        content_type_folder_name = get_folder_name_from_content_type(content_type)

        if unique_id is None:
            try:
                return os.listdir(f"{self.folder}/{content_type_folder_name}")
            except FileNotFoundError:
                return []

        return os.listdir(f"{self.folder}/{content_type_folder_name}/{unique_id}")

    def get_stream(self, content_entry):
        filename = self._get_filename(content_entry)
        if not os.path.isfile(filename):
            raise Exception("Expected file %s to exist for %r", filename, content_entry)

        return Stream(filename, content_entry.filesize)


@click_additional_options
@click.option(
    "--storage-local-folder",
    help="Folder to use for storage. (storage=local only)",
    type=click.Path(dir_okay=True, file_okay=False),
    default="local_storage",
    show_default=True,
)
def click_storage_local(storage_local_folder):
    global _folder

    _folder = storage_local_folder
