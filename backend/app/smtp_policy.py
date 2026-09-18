"""Explicit SMTP loopback trust; never resolve hostnames to make security decisions."""

from ipaddress import IPv6Address, ip_address


def normalize_smtp_host(host: str) -> str:
    # Preserve the name for TLS certificate verification; plaintext pins it below.
    if host.lower() in {"localhost", "localhost."}:
        return "localhost"
    if host.startswith("[") and host.endswith("]"):
        try:
            return str(IPv6Address(host[1:-1]))
        except ValueError:
            pass
    return host


def is_loopback_smtp_host(host: str) -> bool:
    host = normalize_smtp_host(host)
    if host == "localhost":
        return True
    # Scoped literals are not needed for loopback and are deliberately unsupported.
    if "%" in host:
        return False
    try:
        address = ip_address(host)
        # Keep IPv4-mapped IPv6 outside V1, independent of Python's classification.
        return address == IPv6Address("::1") if address.version == 6 else address.is_loopback
    except ValueError:
        return False
