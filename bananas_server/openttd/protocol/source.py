import ipaddress


class Source:
    def __init__(self, protocol, addr, ip, port):
        self.protocol = protocol
        self.addr = addr

        # Normally ip and port are in addr, but in case of Proxy Protocol
        # this might differ.
        self.port = port
        self.ip = ipaddress.ip_address(ip)

        # If using IPv6, IPv4 addresses are mapped like "::fffff:<IPv4>".
        # To have it a bit easier in the logic, convert those instances to an
        # IPv4Address.
        if isinstance(self.ip, ipaddress.IPv6Address) and self.ip.ipv4_mapped:
            self.ip = self.ip.ipv4_mapped

    def __repr__(self):
        return f"Source(addr={self.addr!r}, ip={self.ip!r}, port={self.port!r})"
