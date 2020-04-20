import boto3
import click

from ..helpers.click import click_additional_options
from ..helpers.content_type import get_folder_name_from_content_type

_bucket_name = None


class Stream:
    def __init__(self, fp, filesize):
        self.fp = fp
        self.filesize = filesize

    def read(self, count):
        data = self.fp.read(count)
        self.filesize -= len(data)
        return data

    def eof(self):
        return self.filesize == 0


class Storage:
    def __init__(self):
        if _bucket_name is None:
            raise Exception("--storage-s3-bucket has to be given if storage is s3")

        self._s3 = boto3.client("s3")

    def _get_filename(self, content_entry):
        content_type_folder_name = get_folder_name_from_content_type(content_entry.content_type)
        unique_id = content_entry.unique_id.hex()
        md5sum = content_entry.md5sum.hex()

        return f"{content_type_folder_name}/{unique_id}/{md5sum}.tar.gz"

    def _get_folder_list(self, folder, continuation_token=None):
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
            objects.update(self._get_folder_list(folder, continuation_token=response["NextContinuationToken"]))

        return objects

    def list_folder(self, content_type, unique_id=None):
        content_type_folder_name = get_folder_name_from_content_type(content_type)

        if unique_id is None:
            folders = self._get_folder_list(content_type_folder_name)
            return [folder.split("/")[1] for folder in folders]

        folders = self._get_folder_list(f"{content_type_folder_name}/{unique_id}")
        return [folder.split("/")[2] for folder in folders]

    def get_stream(self, content_entry):
        filename = self._get_filename(content_entry)

        response = self._s3.get_object(Bucket=_bucket_name, Key=filename)
        return Stream(response["Body"], response["ContentLength"])


@click_additional_options
@click.option(
    "--storage-s3-bucket", help="Name of the bucket to upload the files. (storage=s3 only)",
)
def click_storage_s3(storage_s3_bucket):
    global _bucket_name

    _bucket_name = storage_s3_bucket
