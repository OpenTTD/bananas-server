import logging

from .protocol.enums import (
    ContentType,
    PacketTCPContentType,
)
from .protocol.exceptions import (
    PacketInvalidData,
    PacketInvalidSize,
    PacketInvalidType,
)
from .protocol.read import (
    read_uint8,
    read_uint16,
    read_uint32,
)

log = logging.getLogger(__name__)


class ContentInfo:
    def __init__(self, content_id=None, content_type=None, unique_id=None, md5sum=None):
        super().__init__()

        self.content_id = content_id
        self.content_type = content_type
        self.unique_id = unique_id
        self.md5sum = md5sum

    def __repr__(self):
        return (
            f"ContentInfo(content_id={self.content_id!r},"
            f"content_type={self.content_type!r}, "
            f"unique_id={self.unique_id!r}, "
            f"md5sum={self.md5sum!r})"
        )


class OpenTTDProtocolReceive:
    def receive_data(self, queue, data):
        while len(data) > 2:
            length, _ = read_uint16(data)

            if len(data) < length:
                break

            queue.put_nowait(data[0:length])
            data = data[length:]

        return data

    def receive_packet(self, source, data):
        # Check length of packet
        length, data = read_uint16(data)
        if length != len(data) + 2:
            raise PacketInvalidSize(len(data) + 2, length)

        # Check if type is in range
        type, data = read_uint8(data)
        if type >= PacketTCPContentType.PACKET_CONTENT_END:
            raise PacketInvalidType(type)

        # Check if we expect this packet
        type = PacketTCPContentType(type)
        func = getattr(self, f"receive_{type.name}", None)
        if func is None:
            raise PacketInvalidType(type)

        # Process this packet
        kwargs = func(source, data)
        return type, kwargs

    @staticmethod
    def receive_PACKET_CONTENT_CLIENT_INFO_LIST(source, data):
        content_type, data = read_uint8(data)
        openttd_version, data = read_uint32(data)

        if content_type >= ContentType.CONTENT_TYPE_END:
            raise PacketInvalidData("invalid ContentType", content_type)

        content_type = ContentType(content_type)

        if len(data) != 0:
            raise PacketInvalidData("more bytes than expected; remaining: ", len(data))

        return {"content_type": content_type, "openttd_version": openttd_version}

    @staticmethod
    def _receive_client_info(data, count, has_content_id=False, has_content_type_and_unique_id=False, has_md5sum=False):
        content_infos = []
        for _ in range(count):
            content_info = {}

            if has_content_id:
                content_id, data = read_uint32(data)
                content_info["content_id"] = content_id

            if has_content_type_and_unique_id:
                content_type, data = read_uint8(data)
                if content_type >= ContentType.CONTENT_TYPE_END:
                    raise PacketInvalidData("invalid ContentType", content_type)
                content_type = ContentType(content_type)
                content_info["content_type"] = content_type

                unique_id, data = read_uint32(data)
                if content_type == ContentType.CONTENT_TYPE_NEWGRF:
                    # OpenTTD client sends NewGRFs byte-swapped for some reason.
                    # So we swap it back here, as nobody needs to know the
                    # protocol is making a boo-boo.
                    content_info["unique_id"] = unique_id.to_bytes(4, "big")
                elif content_type in (ContentType.CONTENT_TYPE_SCENARIO, ContentType.CONTENT_TYPE_HEIGHTMAP):
                    # We store Scenarios / Heightmaps byte-swapped (to what OpenTTD expects).
                    # This is because otherwise folders are named 01000000, 02000000, which
                    # makes sorting a bit odd, and in general just difficult to read.
                    content_info["unique_id"] = unique_id.to_bytes(4, "big")
                else:
                    content_info["unique_id"] = unique_id.to_bytes(4, "little")

            if has_md5sum:
                md5sum = bytearray()
                for _ in range(16):
                    md5sum_snippet, data = read_uint8(data)
                    md5sum.append(md5sum_snippet)
                md5sum = bytes(md5sum)
                content_info["md5sum"] = md5sum

            content_infos.append(ContentInfo(**content_info))

        return content_infos, data

    @classmethod
    def receive_PACKET_CONTENT_CLIENT_INFO_ID(cls, source, data):
        count, data = read_uint16(data)

        content_infos, data = cls._receive_client_info(data, count, has_content_id=True)

        if len(data) != 0:
            raise PacketInvalidData("more bytes than expected; remaining: ", len(data))

        return {"content_infos": content_infos}

    @classmethod
    def receive_PACKET_CONTENT_CLIENT_INFO_EXTID(cls, source, data):
        count, data = read_uint8(data)

        content_infos, data = cls._receive_client_info(data, count, has_content_type_and_unique_id=True)

        if len(data) != 0:
            raise PacketInvalidData("more bytes than expected; remaining: ", len(data))

        return {"content_infos": content_infos}

    @classmethod
    def receive_PACKET_CONTENT_CLIENT_INFO_EXTID_MD5(cls, source, data):
        count, data = read_uint8(data)

        content_infos, data = cls._receive_client_info(
            data, count, has_content_type_and_unique_id=True, has_md5sum=True
        )

        if len(data) != 0:
            raise PacketInvalidData("more bytes than expected; remaining: ", len(data))

        return {"content_infos": content_infos}

    @classmethod
    def receive_PACKET_CONTENT_CLIENT_CONTENT(cls, source, data):
        count, data = read_uint16(data)

        content_infos, data = cls._receive_client_info(data, count, has_content_id=True)

        if len(data) != 0:
            raise PacketInvalidData("more bytes than expected; remaining: ", len(data))

        return {"content_infos": content_infos}
