class PacketInvalid(Exception):
    """There was an error with this packet. This is a base exception."""


class PacketInvalidSize(PacketInvalid):
    """The size of this packet is not as announced."""


class PacketInvalidType(PacketInvalid):
    """The type of this packet is not valid."""


class PacketInvalidData(PacketInvalid):
    """The packet contains invalid data."""


class PacketTooBig(PacketInvalid):
    """The packet is too big to transmit."""
