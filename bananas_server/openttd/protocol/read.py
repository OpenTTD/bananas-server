import struct

from .exceptions import PacketInvalidData


def validate_length(data, length):
    if len(data) < length:
        raise PacketInvalidData("packet too short")


def read_uint8(data):
    validate_length(data, 1)
    value = struct.unpack("<B", data[0:1])
    return value[0], data[1:]


def read_uint16(data):
    validate_length(data, 2)
    value = struct.unpack("<H", data[0:2])
    return value[0], data[2:]


def read_uint32(data):
    validate_length(data, 4)
    value = struct.unpack("<I", data[0:4])
    return value[0], data[4:]


def read_uint64(data):
    validate_length(data, 8)
    value = struct.unpack("<Q", data[0:8])
    return value[0], data[8:]


def read_bytes(data, count):
    validate_length(data, count)
    return data[0:count], data[count:]


def read_string(data):
    value = b""
    while data[0:1] != b"\x00":
        validate_length(data, 1)
        value += data[0:1]
        data = data[1:]
    return value.decode(), data[1:]
