"""No real mail: remote SMTP always negotiates verified TLS before sending."""

import smtplib
import socket
import ssl
from email.message import EmailMessage

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.services.notifications.delivery import SMTPTransport
from app.smtp_policy import is_loopback_smtp_host

LOOPBACK_HOSTS = ["localhost", "LOCALHOST", "localhost.", "127.0.0.1", "::1", "[::1]", "127.0.0.2"]
REMOTE_HOSTS = [
    "smtp.example.test",
    "mail.example.org",
    "203.0.113.10",
    "192.168.1.10",
    "10.0.0.5",
    "172.16.0.5",
    "smtp.local.example",
    "relay.internal",
    "myhost.local",
    "localhost.example.test",
    "localhost..",
    "[127.0.0.1]",
    "127.1",
    "::",
    "[2001:db8::1]",
    "::ffff:127.0.0.1",
    "::1%lo",
    "localhost:25",
    "",
]


@pytest.mark.parametrize(
    "username,password",
    [("operator", None), (None, "test-secret"), ("operator", ""), ("", "test-secret")],
)
@pytest.mark.parametrize("enabled", [False, True])
def test_smtp_partial_credentials_rejected(username, password, enabled):
    with pytest.raises(ValidationError, match="configured together") as caught:
        Settings(
            _env_file=None,
            notification_smtp_host="localhost",
            notifications_delivery_enabled=enabled,
            notification_smtp_username=username,
            notification_smtp_password=password,
        )
    assert "test-secret" not in str(caught.value)


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("host", ["localhost", "smtp.example.test"])
def test_smtp_auth_requires_tls_even_in_dry_run(enabled, host):
    with pytest.raises(ValidationError, match="requires TLS") as caught:
        Settings(
            _env_file=None,
            notifications_delivery_enabled=enabled,
            notification_smtp_host=host,
            notification_smtp_starttls=False,
            notification_smtp_username="operator",
            notification_smtp_password="test-secret",
        )
    assert "test-secret" not in str(caught.value)


def test_dry_run_inspection_does_not_open_smtp(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Dry run must not connect")

    monkeypatch.setattr(smtplib, "SMTP", forbidden)
    settings = Settings(
        _env_file=None,
        notification_smtp_host="smtp.example.test",
        notification_smtp_username="operator",
        notification_smtp_password="test-secret",
        notification_smtp_starttls=True,
    )
    with pytest.raises(RuntimeError, match="Delivery disabled"):
        SMTPTransport(settings).send(EmailMessage(), "recipient@example.test")


@pytest.mark.parametrize(
    "username,password,tls",
    [
        ("operator", SecretStr("test-secret"), False),
        ("operator", None, True),
        (None, SecretStr("test-secret"), True),
        ("operator", SecretStr(""), True),
        ("", SecretStr("test-secret"), True),
    ],
)
@pytest.mark.parametrize("host", ["localhost", "smtp.example.test"])
def test_transport_defense_before_connection(monkeypatch, settings, username, password, tls, host):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid authentication settings must fail before connect/login")

    monkeypatch.setattr(smtplib, "SMTP", forbidden)
    settings.notifications_delivery_enabled = True
    settings.notification_smtp_host = host
    settings.notification_smtp_username = username
    settings.notification_smtp_password = password
    settings.notification_smtp_starttls = tls
    with pytest.raises(RuntimeError) as caught:
        SMTPTransport(settings).send(EmailMessage(), "recipient@example.test")
    assert "test-secret" not in str(caught.value)


@pytest.mark.parametrize(
    "host,tls,authenticated",
    [(host, False, False) for host in LOOPBACK_HOSTS]
    + [(host, True, auth) for host in ["localhost", "smtp.example.test"] for auth in [False, True]],
)
def test_smtp_order_and_loopback_relay(monkeypatch, host, tls, authenticated):
    calls = []
    settings = Settings(
        _env_file=None,
        notifications_delivery_enabled=True,
        notification_smtp_host=host,
        notification_smtp_starttls=tls,
        notification_smtp_username="operator" if authenticated else "",
        notification_smtp_password="test-secret" if authenticated else "",
    )
    if not authenticated:
        assert settings.notification_smtp_username is None
        assert settings.notification_smtp_password is None
    # Also exercise normalization in the transport after settings are mutated.
    settings.notification_smtp_host = host
    expected_host = host
    if host.lower() in {"localhost", "localhost."}:
        expected_host = "localhost" if tls else "127.0.0.1"
    elif host == "[::1]":
        expected_host = "::1"
    mail = EmailMessage()

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == (expected_host, 587, 20)
            calls.append("connect")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self, context):
            assert context.check_hostname
            assert context.verify_mode == ssl.CERT_REQUIRED
            calls.append("starttls")

        def login(self, username, password):
            assert (username, password) == ("operator", "test-secret")
            calls.append("login")

        def send_message(self, message, from_addr, to_addrs):
            assert message is mail
            assert from_addr == "notifications@kulturbytes.de"
            assert to_addrs == ["recipient@example.test"]
            calls.append("send")

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    SMTPTransport(settings).send(mail, "recipient@example.test")
    assert calls == (
        ["connect", "ehlo"]
        + (["starttls", "ehlo"] if tls else [])
        + (["login"] if authenticated else [])
        + ["send"]
    )


@pytest.mark.parametrize(
    "error",
    [
        smtplib.SMTPNotSupportedError("No TLS"),
        ssl.SSLCertVerificationError("Untrusted certificate"),
    ],
)
def test_starttls_failure_never_falls_back_to_plain_auth(monkeypatch, error):
    settings = Settings(
        _env_file=None,
        notifications_delivery_enabled=True,
        notification_smtp_host="smtp.example.test",
        notification_smtp_username="operator",
        notification_smtp_password="test-secret",
    )

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def ehlo(self):
            pass

        def starttls(self, context):
            raise error

        def login(self, *args):
            pytest.fail("Must not authenticate after failed TLS negotiation")

        def send_message(self, *args, **kwargs):
            pytest.fail("Must not send after failed TLS negotiation")

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    with pytest.raises(type(error)):
        SMTPTransport(settings).send(EmailMessage(), "recipient@example.test")


@pytest.mark.parametrize("host", LOOPBACK_HOSTS + REMOTE_HOSTS)
def test_loopback_policy_without_dns(monkeypatch, host):
    def forbidden(*args, **kwargs):
        pytest.fail("Loopback trust must not depend on DNS")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "gethostbyname", forbidden)
    assert is_loopback_smtp_host(host) is (host in LOOPBACK_HOSTS)


@pytest.mark.parametrize("host", REMOTE_HOSTS)
@pytest.mark.parametrize("enabled", [False, True])
def test_plain_remote_settings_rejected_even_in_dry_run(host, enabled):
    expected = "requires SMTP host" if not host and enabled else "local loopback relay"
    with pytest.raises(ValidationError, match=expected):
        Settings(
            _env_file=None,
            notifications_delivery_enabled=enabled,
            notification_smtp_host=host,
            notification_smtp_starttls=False,
        )


@pytest.mark.parametrize("host", REMOTE_HOSTS)
def test_plain_remote_transport_rejects_before_socket(monkeypatch, settings, host):
    def forbidden(*args, **kwargs):
        pytest.fail("Unsafe configuration must fail before socket creation")

    monkeypatch.setattr(smtplib, "SMTP", forbidden)
    # Deliberately bypass model validation to exercise the independent transport guard.
    settings.notifications_delivery_enabled = True
    settings.notification_smtp_host = host
    settings.notification_smtp_starttls = False
    settings.notification_smtp_username = None
    settings.notification_smtp_password = None
    with pytest.raises(RuntimeError, match="local loopback relay|Delivery disabled"):
        SMTPTransport(settings).send(EmailMessage(), "recipient@example.test")


@pytest.mark.parametrize("tls", [False, True])
def test_enabled_delivery_requires_host(tls):
    with pytest.raises(ValidationError, match="requires SMTP host"):
        Settings(
            _env_file=None,
            notifications_delivery_enabled=True,
            notification_smtp_host=None,
            notification_smtp_starttls=tls,
        )


@pytest.mark.parametrize("host", ["::1", "[::1]"])
def test_ipv6_socket_host_is_unbracketed(host):
    settings = Settings(
        _env_file=None, notification_smtp_host=host, notification_smtp_starttls=False
    )
    assert settings.notification_smtp_host == "::1"
