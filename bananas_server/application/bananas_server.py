import asyncio
import logging

from collections import defaultdict
from concurrent import futures
from prometheus_client import (
    Counter,
    Summary,
)

from openttd_protocol.protocol.content import ContentType
from openttd_protocol.wire.exceptions import SocketClosed

from ..helpers.content_type import get_folder_name_from_content_type
from ..helpers.regions import REGIONS
from ..helpers.safe_filename import safe_filename
from ..storage.exceptions import StreamReadError

log = logging.getLogger(__name__)
stats_download_count = Counter("bananas_server_tcp_download", "Number of downloads", ["content_type", "version"])
stats_download_bytes = Summary(
    "bananas_server_tcp_download_bytes", "Bytes used for downloads", ["content_type", "version"]
)
stats_download_failed = Counter(
    "bananas_server_tcp_download_failed", "Number of failed downloads", ["content_type", "version"]
)
stats_listing_count = Counter("bananas_server_tcp_listing", "Number of listings", ["content_type", "version"])
stats_listing_bytes = Summary("bananas_server_tcp_listing_bytes", "Bytes used for listings", ["content_type"])
stats_info_count = Counter("bananas_server_tcp_info", "Number of info requests", ["content_type"])
stats_info_bytes = Summary("bananas_server_tcp_info_bytes", "Bytes used for info requests", ["content_type"])


IP_TO_VERSION_CACHE = dict()


def get_version_from_source(source):
    if hasattr(source, "version_stats"):
        return source.version_stats

    return IP_TO_VERSION_CACHE.get(source.ip, "unknown")


def set_version_from_source(source, version):
    source.version_stats = version
    IP_TO_VERSION_CACHE[source.ip] = version

    # Ensure this cache doesn't grow out of control.
    if len(IP_TO_VERSION_CACHE) > 10000:
        IP_TO_VERSION_CACHE.pop(next(iter(IP_TO_VERSION_CACHE)))


class Application:
    def __init__(self, storage, index, bootstrap_unique_id):
        super().__init__()

        self.storage = storage
        self.index = index

        if bootstrap_unique_id:
            self._bootstrap_unique_id = bytes.fromhex(bootstrap_unique_id)
        else:
            self._bootstrap_unique_id = None

        self._by_content_id = None
        self._by_content_type = None
        self._by_unique_id = None
        self._by_unique_id_and_md5sum = None

        self._reload_busy = asyncio.Event()
        self._reload_busy.set()

        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.reload())

    def _tags_add_region(self, tags, region):
        tags.add(REGIONS[region]["name"].lower())
        if REGIONS[region]["parent"]:
            self._tags_add_region(tags, REGIONS[region]["parent"])

    async def _send_content_entry(self, source, content_entry):
        # For backwards compatibility, we send classifications as tags.
        tags = set()
        for key, value in content_entry.classification.items():
            if type(value) is str:
                tags.add(value)
            elif type(value) is bool:
                if value:
                    tags.add(key)
            else:
                log.error(f"Unknown type for tag {key}: {type(value)}")
        for region in content_entry.regions:
            self._tags_add_region(tags, region)

        return await source.protocol.send_PACKET_CONTENT_SERVER_INFO(
            content_type=content_entry.content_type,
            content_id=content_entry.content_id,
            filesize=content_entry.filesize,
            name=content_entry.name,
            version=content_entry.version,
            url=content_entry.url,
            description=content_entry.description,
            unique_id=content_entry.unique_id,
            md5sum=content_entry.md5sum,
            dependencies=content_entry.dependencies,
            tags=list(sorted(tags)),
        )

    def get_by_content_id(self, content_id):
        return self._by_content_id.get(content_id)

    def get_by_unique_id(self, content_type, unique_id):
        return self._by_unique_id[content_type].get(unique_id)

    def get_by_unique_id_and_md5sum(self, content_type, unique_id, md5sum):
        return self._by_unique_id_and_md5sum[content_type].get(unique_id, {}).get(md5sum)

    async def receive_PACKET_CONTENT_CLIENT_INFO_LIST(self, source, content_type, openttd_version, branch_versions):
        if openttd_version != 0xFFFFFFFF:
            version_major = (openttd_version >> 24) & 0xFF
            version_minor = (openttd_version >> 20) & 0xF

            if version_major > 16 + 11:
                # Since OpenTTD 12, major is 8 bytes and minor is 4 bytes, and
                # no more patch. The major also needs to be subtracted by 16 to
                # get to the real version.
                version = [version_major - 16, version_minor]
            else:
                # Pre OpenTTD 12 version.
                version_major = (openttd_version >> 28) & 0xF
                version_minor = (openttd_version >> 24) & 0xF
                version_patch = (openttd_version >> 20) & 0xF

                version = [version_major, version_minor, version_patch]

            versions = {
                "vanilla": version,
            }
        else:
            versions = {}

            for branch, version in branch_versions.items():
                if not all([p.isnumeric() for p in version.split(".")]):
                    log.warning(
                        "CLIENT_INFO_LIST version-parts for branch '%s' contains non-integers: %s", branch, version
                    )
                    return

                versions[branch] = [int(p) for p in version.split(".")]

        version_stats = None
        for branch, branch_version in versions.items():
            if branch == "vanilla":
                # Only use "vanilla" if no other branch is given.
                if version_stats is None:
                    version_stats = f"{branch}-" + ".".join([str(v) for v in branch_version])
            else:
                version_stats = f"{branch}-" + ".".join([str(v) for v in branch_version])

        stats_listing_count.labels(
            content_type=get_folder_name_from_content_type(content_type),
            version=version_stats,
        ).inc()
        # Remember version for statistics in later packets.
        set_version_from_source(source, version_stats)

        bootstrap_content_entry = None
        len = 0

        # Make sure the first entry we sent is the bootstrap base graphics,
        # as this is the one the OpenTTD client will use in the bootstrap.
        if content_type == ContentType.CONTENT_TYPE_BASE_GRAPHICS and self._bootstrap_unique_id:
            bootstrap_content_entry = self.get_by_unique_id(
                ContentType.CONTENT_TYPE_BASE_GRAPHICS, self._bootstrap_unique_id
            )

            if not bootstrap_content_entry:
                log.error(f"Bootstrap package with unique-id {self._bootstrap_unique_id} not found")
            else:
                len += await self._send_content_entry(source, bootstrap_content_entry)

        for content_entry in self._by_content_type.get(content_type, []):
            if content_entry == bootstrap_content_entry:
                continue

            # If no compatibility is given, it is compatible with every client.
            # So only run the check if it contains anything.
            if content_entry.compatibility:
                for name, version in versions.items():
                    if name not in content_entry.compatibility:
                        continue

                    min_version, max_version = content_entry.compatibility[name]
                    if min_version and version < min_version:
                        continue
                    if max_version and version >= max_version:
                        continue

                    # Branch is in the compatibility matrix and we are in the
                    # version range. We break here, so the else below is not
                    # executed. This means we add the entry to the list.
                    break
                else:
                    # We never found a branch for which we were compatible. So
                    # we will be skipping this entry.
                    continue

            len += await self._send_content_entry(source, content_entry)

        stats_listing_bytes.labels(content_type=get_folder_name_from_content_type(content_type)).observe(len)

    async def receive_PACKET_CONTENT_CLIENT_INFO_EXTID(self, source, content_infos):
        for content_info in content_infos:
            content_entry = self.get_by_unique_id(content_info.content_type, content_info.unique_id)
            if content_entry:
                stats_info_count.labels(
                    content_type=get_folder_name_from_content_type(content_entry.content_type)
                ).inc()
                len = await self._send_content_entry(source, content_entry)
                stats_info_bytes.labels(
                    content_type=get_folder_name_from_content_type(content_entry.content_type)
                ).observe(len)

    async def receive_PACKET_CONTENT_CLIENT_INFO_EXTID_MD5(self, source, content_infos):
        for content_info in content_infos:
            content_entry = self.get_by_unique_id_and_md5sum(
                content_info.content_type, content_info.unique_id, content_info.md5sum
            )
            if content_entry:
                stats_info_count.labels(
                    content_type=get_folder_name_from_content_type(content_entry.content_type)
                ).inc()
                len = await self._send_content_entry(source, content_entry)
                stats_info_bytes.labels(
                    content_type=get_folder_name_from_content_type(content_entry.content_type)
                ).observe(len)

    async def receive_PACKET_CONTENT_CLIENT_INFO_ID(self, source, content_infos):
        for content_info in content_infos:
            content_entry = self.get_by_content_id(content_info.content_id)
            if content_entry:
                stats_info_count.labels(
                    content_type=get_folder_name_from_content_type(content_entry.content_type)
                ).inc()
                len = await self._send_content_entry(source, content_entry)
                stats_info_bytes.labels(
                    content_type=get_folder_name_from_content_type(content_entry.content_type)
                ).observe(len)

    async def receive_PACKET_CONTENT_CLIENT_CONTENT(self, source, content_infos):
        for content_info in content_infos:
            content_entry = self.get_by_content_id(content_info.content_id)
            if not content_entry:
                continue

            stats_download_count.labels(
                content_type=get_folder_name_from_content_type(content_entry.content_type),
                version=get_version_from_source(source),
            ).inc()

            try:
                with self.storage.get_stream(content_entry) as stream:
                    await source.protocol.send_PACKET_CONTENT_SERVER_CONTENT(
                        content_type=content_entry.content_type,
                        content_id=content_entry.content_id,
                        filesize=content_entry.filesize,
                        filename=safe_filename(content_entry),
                        stream=stream,
                    )
            except asyncio.CancelledError:
                stats_download_failed.labels(
                    content_type=get_folder_name_from_content_type(content_entry.content_type),
                    version=get_version_from_source(source),
                ).inc()

                # Our coroutine is cancelled, pass it on the the caller.
                raise
            except StreamReadError:
                stats_download_failed.labels(
                    content_type=get_folder_name_from_content_type(content_entry.content_type),
                    version=get_version_from_source(source),
                ).inc()

                # Reading from the backend failed; we don't have many options
                # except to abort the connection and hope the user retries.
                raise SocketClosed
            except SocketClosed:
                stats_download_failed.labels(
                    content_type=get_folder_name_from_content_type(content_entry.content_type),
                    version=get_version_from_source(source),
                ).inc()

                # The user terminated it's connection; our caller knows how to
                # handle this signal.
                raise
            except Exception:
                stats_download_failed.labels(
                    content_type=get_folder_name_from_content_type(content_entry.content_type),
                    version=get_version_from_source(source),
                ).inc()

                log.exception("Error with storage, aborting for this client ...")
                raise SocketClosed

            stats_download_bytes.labels(
                content_type=get_folder_name_from_content_type(content_entry.content_type),
                version=get_version_from_source(source),
            ).observe(content_entry.filesize)

    async def reload(self):
        await self._reload_busy.wait()
        self._reload_busy.clear()

        try:
            reload_helper = ReloadHelper(self.storage, self.index)
            reload_helper.prepare()

            # Run the reload in a new process, so we don't block the rest of the
            # server while doing this job.
            loop = asyncio.get_event_loop()
            with futures.ProcessPoolExecutor(max_workers=1) as executor:
                task = loop.run_in_executor(executor, reload_helper.reload)
                (
                    self._by_content_id,
                    self._by_content_type,
                    self._by_unique_id,
                    self._by_unique_id_and_md5sum,
                ) = await task
        finally:
            self._reload_busy.set()


class ReloadHelper:
    def __init__(self, storage, index):
        self.storage = storage
        self.index = index

    def _get_md5sum_mapping(self):
        log.info("Building md5sum mapping")
        md5sum_mapping = defaultdict(lambda: defaultdict(dict))

        for content_type in ContentType:
            if content_type == ContentType.CONTENT_TYPE_END:
                continue

            for unique_id_str in self.storage.list_folder(content_type):
                unique_id = bytes.fromhex(unique_id_str)

                for filename in self.storage.list_folder(content_type, unique_id_str):
                    md5sum, _, _ = filename.partition(".")

                    md5sum_partial = bytes.fromhex(md5sum[0:8])
                    md5sum = bytes.fromhex(md5sum)

                    md5sum_mapping[content_type][unique_id][md5sum_partial] = md5sum

        # defaultdict() cannot be pickled, so convert to a normal dict.
        return {key: dict(value) for key, value in md5sum_mapping.items()}

    def prepare(self):
        self.storage.clear_cache()

    def reload(self):
        md5sum_mapping = self._get_md5sum_mapping()
        return self.index.reload(md5sum_mapping)
