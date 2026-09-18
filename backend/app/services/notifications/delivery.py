"""SMTP is at-least-once: acceptance and the admin commit cannot be atomic."""

import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, formataddr
from typing import Any, Protocol

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_tables import notification_delivery as d
from app.config import Settings

RETRY_DELAYS = (
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=12),
)


class Transport(Protocol):
    def send(self, message: EmailMessage, recipient: str) -> None: ...


class SMTPTransport:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, message: EmailMessage, recipient: str) -> None:
        s = self.settings
        if not s.notifications_delivery_enabled or not s.notification_smtp_host:
            raise RuntimeError("Delivery disabled")
        with smtplib.SMTP(
            s.notification_smtp_host,
            s.notification_smtp_port,
            timeout=s.notification_smtp_timeout_seconds,
        ) as smtp:
            smtp.ehlo()
            if s.notification_smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if s.notification_smtp_username:
                smtp.login(
                    s.notification_smtp_username,
                    s.notification_smtp_password.get_secret_value()
                    if s.notification_smtp_password
                    else "",
                )
            smtp.send_message(
                message, from_addr=s.notification_smtp_from_email, to_addrs=[recipient]
            )


def message(delivery: dict[str, Any], settings: Settings) -> EmailMessage:
    mail = delivery["snapshot"]["mail"]
    email = EmailMessage()
    sender = str(TypeAdapter(EmailStr).validate_python(settings.notification_smtp_from_email))
    recipient = str(TypeAdapter(EmailStr).validate_python(delivery["recipient"]))
    email["From"] = formataddr((settings.notification_smtp_from_name, sender))
    email["To"] = recipient
    if stamp := delivery["snapshot"].get("composed_at"):
        email["Date"] = format_datetime(datetime.fromisoformat(stamp))
    email["Subject"] = mail["subject"]
    email["Message-ID"] = f"<notification-delivery-{delivery['id']}@kulturbytes.de>"
    email.set_content(mail["text"])
    email.add_alternative(mail["html"], subtype="html")
    return email


def failure(exc: Exception, attempt: int, now: datetime) -> tuple[str, datetime | None, str]:
    code: int | None = None
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [detail[0] for detail in exc.recipients.values()]
        code = codes[0] if codes else None
    elif isinstance(exc, smtplib.SMTPResponseException):
        code = exc.smtp_code
    permanent = (
        isinstance(exc, smtplib.SMTPRecipientsRefused) and code is not None and 500 <= code < 600
    )
    # Fixed categories only: never stringify SMTP exceptions (may contain recipient,
    # credentials, arbitrary server text or an entire protocol exchange).
    detail = (
        f"smtp_{code}"
        if code is not None
        else "smtp_timeout"
        if isinstance(exc, TimeoutError)
        else "smtp_connection_failure"
    )
    if permanent or attempt >= 5:
        return "permanent_failure", None, detail
    return "failed", now + RETRY_DELAYS[attempt - 1], detail


async def finish(
    admin: AsyncConnection, delivery: dict[str, Any], now: datetime, error: Exception | None = None
) -> bool:
    status, retry, detail = (
        failure(error, delivery["attempt_count"], now) if error else ("sent", None, None)
    )
    async with admin.begin():
        result = await admin.execute(
            update(d)
            .where(
                d.c.id == delivery["id"],
                d.c.status == "sending",
                d.c.worker_id == delivery["worker_id"],
                d.c.lease_until > now,
            )
            .values(
                status=status,
                sent_at=now if error is None else None,
                next_attempt_at=retry,
                last_error=detail,
                worker_id=None,
                lease_until=None,
                updated_at=now,
            )
        )
        return result.rowcount == 1
