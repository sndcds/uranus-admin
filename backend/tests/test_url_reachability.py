import socket
import ssl
from unittest.mock import AsyncMock

import httpcore
import pytest

from app.services.url_reachability import (
    MAX_BYTES,
    DNSFailure,
    PublicNetworkBackend,
    check_url,
    public_address,
    resolve,
)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "127.5.6.7",
        "::1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.0.1",
        "169.254.169.254",
        "169.254.1.1",
        "fe80::1",
        "fc00::1",
        "ff02::1",
        "224.0.0.1",
        "0.0.0.0",
        "::",
        "100.64.0.1",
        "192.0.2.1",
        "::ffff:127.0.0.1",
        "64:ff9b::a00:1",
        "2002:7f00:1::",
    ],
)
def test_nonpublic_ranges(ip):
    assert not public_address(ip)


def response(code=200, headers="", body=b"ok"):
    return f"HTTP/1.1 {code} Status\r\nContent-Length: {len(body)}\r\n{headers}\r\n".encode() + body


def network(monkeypatch, responses, addresses=None):
    connections, requests, tls = [], [], []

    async def resolver(host, port):
        return addresses.get(host, ["93.184.216.34"]) if addresses else ["93.184.216.34"]

    class Stream(httpcore.AsyncMockStream):
        async def write(self, buffer, timeout=None):  # noqa: ASYNC109 - transport interface
            requests.append(buffer)

        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):  # noqa: ASYNC109
            tls.append((server_hostname, ssl_context.verify_mode, ssl_context.check_hostname))
            return self

    async def connect(self, host, port, *args):
        connections.append((host, port))
        return Stream([responses.pop(0)])

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    return PublicNetworkBackend(resolver), connections, requests, tls


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "http://127.0.0.1",
        "http://[::1]",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1",
        "http://[fc00::1]",
        "http://private.test",
        "http://mixed.test",
        "file:///etc/passwd",
        "ftp://public.test",
        "http://user:password@public.test",
        "https://public.test?access_token=secret",
        "http://public.test:8080",
    ],
)
async def test_targets_blocked_before_connect(monkeypatch, url):
    host = __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(url).hostname
    addresses = {host: [host] if host and (":" in host or host[0].isdigit()) else ["10.0.0.1"]}
    if host == "mixed.test":
        addresses[host] = ["93.184.216.34", "10.0.0.1"]
    backend, connections, _, _ = network(monkeypatch, [], addresses)
    assert (await check_url(url, backend)).status == "invalid_target"
    assert connections == []


async def test_ip_pinning_host_and_tls_identity(monkeypatch):
    backend, connections, requests, tls = network(monkeypatch, [response()])
    resolver = AsyncMock(side_effect=[["93.184.216.34"], ["127.0.0.1"]])
    backend.resolver = resolver
    assert (await check_url("https://public.test/page", backend)).status == "reachable"
    assert connections == [("93.184.216.34", 443)]
    assert resolver.await_count == 1
    assert tls == [("public.test", ssl.CERT_REQUIRED, True)]
    wire = b"".join(requests).lower()
    assert b"host: public.test" in wire
    assert b"authorization:" not in wire and b"cookie:" not in wire


@pytest.mark.parametrize(
    "code,status",
    [
        (200, "reachable"),
        (206, "reachable"),
        (403, "blocked"),
        (429, "rate_limited"),
        (404, "unreachable"),
        (500, "unreachable"),
    ],
)
async def test_status_semantics(monkeypatch, code, status):
    backend, _, _, _ = network(monkeypatch, [response(code)])
    result = await check_url("http://public.test", backend)
    assert result.status == status and result.status_code == code


async def test_redirects_revalidate_every_connection(monkeypatch):
    backend, connections, _, _ = network(
        monkeypatch, [response(301, "Location: https://other.test/final\r\n"), response()]
    )
    result = await check_url("https://public.test", backend)
    assert result.status == "reachable" and result.redirect_target == "https://other.test/final"
    assert len(connections) == 2
    backend, connections, _, _ = network(
        monkeypatch,
        [response(302, "Location: http://private.test\r\n")],
        {"private.test": ["10.0.0.1"]},
    )
    assert (await check_url("http://public.test", backend)).status == "invalid_target"
    assert len(connections) == 1


async def test_redirect_loop_and_limit(monkeypatch):
    backend, connections, _, _ = network(monkeypatch, [response(301, "Location: /\r\n")])
    assert (await check_url("http://public.test/", backend)).failure_type == "redirect_loop"
    backend, connections, _, _ = network(
        monkeypatch, [response(301, f"Location: /{i}\r\n") for i in range(6)]
    )
    assert (await check_url("http://public.test/", backend)).failure_type == "too_many_redirects"
    assert len(connections) == 6


async def test_limits_dns_tls_and_timeouts(monkeypatch):
    backend, _, _, _ = network(monkeypatch, [response(body=b"x" * (MAX_BYTES + 1))])
    assert (await check_url("http://public.test", backend)).status == "too_large"
    for error, status in [
        (TimeoutError(), "timeout"),
        (DNSFailure(), "dns_error"),
        (ssl.SSLError(), "tls_error"),
    ]:
        backend.resolver = AsyncMock(side_effect=error)
        assert (await check_url("https://public.test", backend)).status == status


async def test_dns_error_sanitized(monkeypatch):
    import asyncio

    monkeypatch.setattr(
        asyncio.get_running_loop(), "getaddrinfo", AsyncMock(side_effect=socket.gaierror("secret"))
    )
    with pytest.raises(DNSFailure) as exc:
        await resolve("public.test", 80)
    assert str(exc.value) == ""
