import logging
import random

from collections import defaultdict

from ..openttd.protocol.enums import ContentType

log = logging.getLogger(__name__)


class Application:
    def __init__(self, storage, index):
        super().__init__()

        self.storage = storage
        self.index = index
        self.protocol = None

        self._md5sum_mapping = defaultdict(lambda: defaultdict(dict))

        self._id_mapping = defaultdict(lambda: defaultdict(dict))
        self._by_content_id = {}
        self._by_content_type = defaultdict(list)
        self._by_unique_id = defaultdict(dict)
        self._by_unique_id_and_md5sum = defaultdict(lambda: defaultdict(dict))

        self.reload()

    def _send_content_entry(self, source, content_entry):
        source.protocol.send_PACKET_CONTENT_SERVER_INFO(
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
            tags=content_entry.tags,
        )

    def receive_PACKET_CONTENT_CLIENT_INFO_LIST(self, source, content_type, openttd_version):
        version_major = (openttd_version >> 28) & 0xF
        version_minor = (openttd_version >> 24) & 0xF
        version_patch = (openttd_version >> 20) & 0xF
        version = (version_major, version_minor, version_patch)

        for content_entry in self._by_content_type[content_type]:
            if content_entry.min_version and version < content_entry.min_version:
                continue
            if content_entry.max_version and version >= content_entry.max_version:
                continue

            self._send_content_entry(source, content_entry)

    def receive_PACKET_CONTENT_CLIENT_INFO_EXTID(self, source, content_infos):
        for content_info in content_infos:
            content_entry = self._by_unique_id[content_info.content_type].get(content_info.unique_id)
            if content_entry:
                self._send_content_entry(source, content_entry)

    def receive_PACKET_CONTENT_CLIENT_INFO_EXTID_MD5(self, source, content_infos):
        for content_info in content_infos:
            content_entry = (
                self._by_unique_id_and_md5sum[content_info.content_type]
                .get(content_info.unique_id, {})
                .get(content_info.md5sum)
            )
            if content_entry:
                self._send_content_entry(source, content_entry)

    def receive_PACKET_CONTENT_CLIENT_INFO_ID(self, source, content_infos):
        for content_info in content_infos:
            content_entry = self._by_content_id.get(content_info.content_id)
            if content_entry:
                self._send_content_entry(source, content_entry)

    def receive_PACKET_CONTENT_CLIENT_CONTENT(self, source, content_infos):
        for content_info in content_infos:
            content_entry = self._by_content_id[content_info.content_id]

            try:
                stream = self.storage.get_stream(content_entry)
            except Exception:
                log.exception("Error with storage, aborting for this client ...")
                return

            source.protocol.send_PACKET_CONTENT_SERVER_CONTENT(
                content_type=content_entry.content_type,
                content_id=content_entry.content_id,
                filesize=content_entry.filesize,
                filename=f"{content_entry.name} - {content_entry.version}",
                stream=stream,
            )

    def get_by_content_id(self, content_id):
        return self._by_content_id.get(content_id)

    def get_by_unique_id_and_md5sum(self, content_type, unique_id, md5sum):
        return self._by_unique_id_and_md5sum[content_type].get(unique_id, {}).get(md5sum)

    def reload_md5sum_mapping(self):
        for content_type in ContentType:
            if content_type == ContentType.CONTENT_TYPE_END:
                continue

            for unique_id_str in self.storage.list_folder(content_type):
                unique_id = bytes.fromhex(unique_id_str)

                for filename in self.storage.list_folder(content_type, unique_id_str):
                    md5sum, _, _ = filename.partition(".")

                    md5sum_partial = bytes.fromhex(md5sum[0:8])
                    md5sum = bytes.fromhex(md5sum)

                    self._md5sum_mapping[content_type][unique_id][md5sum_partial] = md5sum

    def reload(self):
        self.index.reload(self)

    def clear(self):
        self._by_content_id.clear()
        self._by_content_type.clear()
        self._by_unique_id.clear()
        self._by_unique_id_and_md5sum.clear()
        self._md5sum_mapping.clear()

    def _get_next_content_id(self, content_type, unique_id, md5sum):
        # Cache the result for the livetime of this process. This means that
        # if we reload, we keep the content_ids as they were. This avoids
        # clients having content_ids that are no longer valid.
        # If this process cycles, this mapping is lost. That can lead to some
        # clients having to restart their OpenTTD, but as this is expected to
        # be a rare event, it should be fine.
        content_id = self._id_mapping[content_type][unique_id].get(md5sum)
        if content_id is not None:
            return content_id

        # Pick a random content_id and check if it is not used. The total
        # amount of available content at the time of writing is around the
        # 5,000 entries. So the chances of hitting an existing number is
        # very small, and this should be done pretty quick.
        while True:
            content_id = random.randrange(0, 2 ** 31)
            if content_id not in self._by_content_id:
                self._id_mapping[content_type][unique_id][md5sum] = content_id
                return content_id
