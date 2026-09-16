"""Bounded public-web observations with DNS validation at the actual connect boundary."""

import asyncio
import ipaddress
import socket
import ssl
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpcore
import httpx

from app.services.quality.urls import url_problem

MAX_BYTES = 256 * 1024
MAX_REDIRECTS = 5
TOTAL_SECONDS = 20
Resolver = Callable[[str, int], Awaitable[list[str]]]


class InvalidTarget(Exception):
    pass


class DNSFailure(Exception):
    pass


async def resolve(host: str, port: int) -> list[str]:
    try:
        rows = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise DNSFailure() from None
    return sorted({str(row[4][0]) for row in rows})


def public_address(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        # Reject transition/tunnel forms, including IPv4 mapped and NAT64 ambiguity.
        return ip in ipaddress.ip_network("2000::/3") and not ip.sixtofour and not ip.teredo
    return True


def normalized_url(value: str) -> str:
    if len(value) > 4096 or url_problem(value) is not None:
        raise InvalidTarget()
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        not host
        or parsed.username is not None
        or parsed.password is not None
        or host == "localhost"
        or host.endswith((".localhost", ".local", ".internal"))
        or parsed.port not in {None, 80, 443}
        or any(
            key.lower()
            in {
                "token",
                "access_token",
                "refresh_token",
                "password",
                "secret",
                "api_key",
                "key",
                "signature",
            }
            for key, _ in parse_qsl(parsed.query)
        )
    ):
        raise InvalidTarget()
    return str(httpx.URL(value).copy_with(fragment=None))


class PublicNetworkBackend(httpcore.AnyIOBackend):
    def __init__(self, resolver: Resolver = resolve) -> None:
        self.resolver = resolver

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - HTTPCore interface
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        async with asyncio.timeout(min(timeout or 4, 4)):
            addresses = await self.resolver(host, port)
            if not addresses:
                raise DNSFailure()
            if not all(public_address(ip) for ip in addresses):
                raise InvalidTarget()
            # Numeric IP only: the actual connection cannot resolve host again. HTTPCore
            # retains the original origin for Host and verified TLS server_hostname.
            return await super().connect_tcp(
                addresses[0], port, timeout, local_address, socket_options
            )


@dataclass(frozen=True)
class Observation:
    status: str
    status_code: int | None = None
    redirect_target: str | None = None
    failure_type: str | None = None


async def check_url(url: str, backend: httpcore.AsyncNetworkBackend | None = None) -> Observation:
    """No credentials, cookies, environment proxies, automatic redirects or body buffering."""
    target = None
    try:
        current = normalized_url(url)
        visited: set[str] = set()
        async with (
            asyncio.timeout(TOTAL_SECONDS),
            httpcore.AsyncConnectionPool(
                network_backend=backend or PublicNetworkBackend(),
                ssl_context=ssl.create_default_context(),
                max_connections=1,
                max_keepalive_connections=0,
                retries=0,
            ) as client,
        ):
            for hop in range(MAX_REDIRECTS + 1):
                current = normalized_url(current)
                if current in visited:
                    return Observation(
                        "redirect_limit", redirect_target=target, failure_type="redirect_loop"
                    )
                visited.add(current)
                async with client.stream(
                    "GET",
                    current,
                    headers={
                        "User-Agent": "Kulturbytes-Admin-URL-Check/1.0",
                        "Accept-Encoding": "identity",
                        "Range": f"bytes=0-{MAX_BYTES - 1}",
                    },
                    extensions={
                        "timeout": {"connect": 4.0, "read": 6.0, "write": 4.0, "pool": 4.0}
                    },
                ) as response:
                    code = response.status
                    if code in {301, 302, 303, 307, 308}:
                        location = next(
                            (
                                v.decode("latin1")
                                for k, v in response.headers
                                if k.lower() == b"location"
                            ),
                            None,
                        )
                        if location is None:
                            return Observation(
                                "unreachable", code, failure_type="missing_redirect_target"
                            )
                        if hop == MAX_REDIRECTS:
                            return Observation("redirect_limit", code, target, "too_many_redirects")
                        # Revalidate each redirect and actual connect; never forward auth.
                        current = normalized_url(urljoin(current, location))
                        target = current
                        continue
                    if code in {401, 403}:
                        return Observation("blocked", code, target)
                    if code == 429:
                        return Observation("rate_limited", code, target)
                    size = 0
                    async for chunk in response.aiter_stream():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            return Observation("too_large", code, target, "response_limit")
                    if 200 <= code < 300:
                        return Observation("reachable", code, target)
                    return Observation("unreachable", code, target, "http_status")
    except InvalidTarget:
        return Observation("invalid_target", failure_type="ssrf_policy")
    except DNSFailure:
        return Observation("dns_error", failure_type="dns_error")
    except (TimeoutError, httpcore.TimeoutException):
        return Observation("timeout", failure_type="timeout")
    except (httpcore.ConnectError, ssl.SSLError) as exc:
        cause: BaseException | None = exc
        while cause is not None:
            if isinstance(cause, ssl.SSLError):
                return Observation("tls_error", failure_type="tls_error")
            cause = cause.__cause__
        return Observation("unreachable", failure_type="connect_error")
    except (httpcore.NetworkError, httpcore.ProtocolError, ValueError):
        return Observation("unreachable", failure_type="network_error")
    return Observation("redirect_limit", failure_type="too_many_redirects")
