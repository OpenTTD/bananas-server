import boto3
import click

from urllib3.exceptions import ProtocolError

from .exceptions import StreamReadError
from ..helpers.click import click_additional_options
from ..helpers.content_type import get_folder_name_from_content_type

_bucket_name = None


class Stream:
    def __init__(self, fp, filesize):
        self.fp = fp
        self.filesize = filesize

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        pass

    def read(self, count):
        try:
            data = self.fp.read(count)
        except ProtocolError:
            raise StreamReadError
        self.filesize -= len(data)
        return data

    def eof(self):
        return self.filesize == 0


class Storage:
    def __init__(self):
        if _bucket_name is None:
            raise Exception("--storage-s3-bucket has to be given if storage is s3")

        self._s3_cache = None
        self._folder_cache = None

    @property
    def _s3(self):
        # This class will be pickled to be used by ProcessPoolExecutor(). To
        # prevent the unpicklable S3 client having to be transmitted over the
        # wire, create it only after the process is created.
        if not self._s3_cache:
            self._s3_cache = boto3.client("s3")

        return self._s3_cache

    def _get_filename(self, content_entry):
        content_type_folder_name = get_folder_name_from_content_type(content_entry.content_type)
        unique_id = content_entry.unique_id.hex()
        md5sum = content_entry.md5sum.hex()

        return f"{content_type_folder_name}/{unique_id}/{md5sum}.tar.gz"

    def _get_full_folder_list(self, folder, continuation_token=None):
        kwargs = {}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        response = self._s3.list_objects_v2(Bucket=_bucket_name, Prefix=folder, **kwargs)
        if response["KeyCount"] == 0:
            return set()

        objects = set()
        for obj in response["Contents"]:
            objects.add(obj["Key"])

        if response.get("NextContinuationToken"):
            objects.update(self._get_full_folder_list(folder, continuation_token=response["NextContinuationToken"]))

        return objects

    def _get_folder_list(self, folder_search):
        # List all files on the S3, and cache it. Otherwise we will be doing
        # a lot of API calls, and that is very slow.
        if self._folder_cache is None:
            self._folder_cache = self._get_full_folder_list("")

        # Filter out the request based on the cache. We are a generator to
        # not create yet-an-other-list in memory.
        for folder in self._folder_cache:
            if folder.startswith(folder_search):
                yield folder

    def clear_cache(self):
        # Reset the s3 instance, as it is not pickable. We are called just
        # before a new process is created. On next use, a new object is
        # created. Although this takes a few more cycles, the amount of times
        # this happens makes it not worth mentioning.
        self._s3_cache = None
        self._folder_cache = None

    def list_folder(self, content_type, unique_id=None):
        content_type_folder_name = get_folder_name_from_content_type(content_type)

        if unique_id is None:
            folders = self._get_folder_list(content_type_folder_name)
            for folder in folders:
                yield folder.split("/")[1]
        else:
            folders = self._get_folder_list(f"{content_type_folder_name}/{unique_id}")
            for folder in folders:
                yield folder.split("/")[2]

    def get_stream(self, content_entry):
        filename = self._get_filename(content_entry)

        response = self._s3.get_object(Bucket=_bucket_name, Key=filename)
        return Stream(response["Body"], response["ContentLength"])


@click_additional_options
@click.option(
    "--storage-s3-bucket",
    help="Name of the bucket to upload the files. (storage=s3 only)",
)
def click_storage_s3(storage_s3_bucket):
    global _bucket_name

    _bucket_name = storage_s3_bucket
