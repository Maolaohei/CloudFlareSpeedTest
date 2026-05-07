import ipaddress
import random
import re

_IP_PATTERN = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
_CIDR_PATTERN = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$")


def is_ip(s: str) -> bool:
    return bool(_IP_PATTERN.match(s))


def is_cidr(s: str) -> bool:
    return bool(_CIDR_PATTERN.match(s))


def expand_cidr(cidr: str, count: int = 100) -> list[str]:
    """Randomly pick `count` IPv4 addresses from the given CIDR range.

    Uses random offset sampling — never materialises all hosts, so it is
    safe for any prefix length (including /8).
    """
    net = ipaddress.ip_network(cidr, strict=False)
    network_int = int(net.network_address)
    prefix_len = net.prefixlen

    # /31 and /32 have 0 usable hosts
    if prefix_len >= 31:
        hosts = list(net.hosts())
        return [str(h) for h in hosts[:count]]

    num_hosts = (1 << (32 - prefix_len)) - 2  # exclude network + broadcast
    if num_hosts <= 0:
        return []

    if count >= num_hosts:
        return [str(ipaddress.IPv4Address(network_int + i))
                for i in range(1, num_hosts + 1)]

    offsets = random.sample(range(1, num_hosts + 1), count)
    return [str(ipaddress.IPv4Address(network_int + o)) for o in offsets]


def is_valid_ipv4(ip: str) -> bool:
    try:
        ipaddress.IPv4Address(ip)
        return True
    except ipaddress.AddressValueError:
        return False


# ── Cloudflare IP range filter ──────────────────────────────────

_cf_ranges: list[ipaddress.IPv4Network] | None = None


def load_cf_ranges(filepath: str = "cf_ip_ranges.txt") -> list[ipaddress.IPv4Network]:
    """Load Cloudflare IP ranges from file (one CIDR per line)."""
    global _cf_ranges
    networks = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if is_cidr(line):
                    try:
                        networks.append(ipaddress.IPv4Network(line, strict=False))
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    _cf_ranges = networks
    return networks


def is_cf_ip(ip: str) -> bool:
    """Check if an IP belongs to a known Cloudflare range."""
    if _cf_ranges is None:
        return True  # ranges not loaded → don't filter
    if not _cf_ranges:
        return True
    try:
        addr = ipaddress.IPv4Address(ip)
        return any(addr in net for net in _cf_ranges)
    except ipaddress.AddressValueError:
        return False
