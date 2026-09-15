import re
from ipaddress import IPv6Address
from typing import Literal
from urllib.parse import urlsplit

URLProblem = Literal[
    "missing_scheme", "disallowed_scheme", "missing_host", "embedded_whitespace", "parse_error"
]


def url_problem(value: str | None) -> URLProblem | None:
    if value is None or not value.strip():
        return None  # Optional absence is not a syntax finding.
    value = value.strip()
    if any(char.isspace() for char in value):
        return "embedded_whitespace"
    if any(ord(char) < 32 or ord(char) == 127 for char in value) or "\\" in value:
        return "parse_error"
    try:
        parsed = urlsplit(value)
        if not parsed.scheme:
            return "missing_scheme"
        if parsed.scheme.lower() not in {"http", "https"}:
            # A domain:port without // is also missing its HTTP(S) schema.
            if re.match(r"^[^/:]+\.[^/:]+:\d+(?:/|$)", value):
                return "missing_scheme"
            return "disallowed_scheme"
        if not parsed.hostname:
            return "missing_host"
        _ = parsed.port  # Reject invalid/out-of-range ports.
        host = parsed.hostname.encode("idna").decode()
        if ":" in host:
            IPv6Address(host)
        elif len(host) > 253 or any(
            not re.fullmatch(r"[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?", label)
            for label in host.rstrip(".").split(".")
        ):
            return "parse_error"
        if re.search(r"%(?![0-9a-fA-F]{2})", value) or "%" in parsed.hostname:
            return "parse_error"
    except (ValueError, UnicodeError):
        return "parse_error"
    return None


def valid_online(value: str | None) -> bool:
    return bool(value and value.strip() and url_problem(value) is None)
