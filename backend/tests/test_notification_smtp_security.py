"""No sockets or real mail: authenticated SMTP must negotiate verified TLS first."""

import smtplib
import ssl
from email.message import EmailMessage

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.services.notifications.delivery import SMTPTransport


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


def test_smtp_auth_requires_tls_before_enabling_delivery():
    with pytest.raises(ValidationError, match="requires TLS") as caught:
        Settings(
            _env_file=None,
            notifications_delivery_enabled=True,
            notification_smtp_host="smtp.example.test",
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
        notification_smtp_starttls=False,
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
def test_transport_defense_before_connection(monkeypatch, settings, username, password, tls):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid authentication settings must fail before connect/login")

    monkeypatch.setattr(smtplib, "SMTP", forbidden)
    settings.notifications_delivery_enabled = True
    settings.notification_smtp_host = "smtp.example.test"
    settings.notification_smtp_username = username
    settings.notification_smtp_password = password
    settings.notification_smtp_starttls = tls
    with pytest.raises(RuntimeError) as caught:
        SMTPTransport(settings).send(EmailMessage(), "recipient@example.test")
    assert "test-secret" not in str(caught.value)


@pytest.mark.parametrize("authenticated", [False, True])
def test_smtp_order_and_trusted_local_relay(monkeypatch, authenticated):
    calls = []
    settings = Settings(
        _env_file=None,
        notifications_delivery_enabled=True,
        notification_smtp_host="localhost",
        notification_smtp_starttls=authenticated,
        notification_smtp_username="operator" if authenticated else "",
        notification_smtp_password="test-secret" if authenticated else "",
    )
    if not authenticated:
        assert settings.notification_smtp_username is None
        assert settings.notification_smtp_password is None
    mail = EmailMessage()

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("localhost", 587, 20)
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
        ["connect", "ehlo", "starttls", "ehlo", "login", "send"]
        if authenticated
        else ["connect", "ehlo", "send"]
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
