import struct

from .exceptions import PacketTooBig

SEND_MTU = 1460


def write_init(type):
    return b"\x00\x00" + struct.pack("<B", type)


def write_uint8(data, value):
    return data + struct.pack("<B", value)


def write_uint16(data, value):
    return data + struct.pack("<H", value)


def write_uint32(data, value):
    return data + struct.pack("<I", value)


def write_uint64(data, value):
    return data + struct.pack("<Q", value)


def write_string(data, value):
    return data + value.encode() + b"\x00"


def write_presend(data):
    if len(data) > SEND_MTU:
        raise PacketTooBig(len(data))
    return struct.pack("<H", len(data)) + data[2:]
