"""One HTML structure, escaped source values and complete plain text."""

import re
from html import escape
from uuid import UUID

from app.config import Settings
from app.schemas.notifications import NotificationPayload, NotificationPreview
from app.services.notifications.actions import recipient_action
from app.services.notifications.localization import catalogue, format_date
from app.services.notifications.policy import EXTERNAL_POLICY

# Visual reference: Uranus 5a5ac813eec708c99de6962aa05a2357535117b0.
# Presentation only: do not bump the semantic TEMPLATE_VERSION for these styles.
EMAIL_CSS = """
body {
    margin: 0;
    padding: 0;
    background-color: #f9fafb;
    color: #374151;
    font-family: Arial, Helvetica, sans-serif;
    line-height: 1.5;
}

.email-container {
    max-width: 600px;
    margin: 0 auto;
    padding: 40px 24px;
}

.email-content {
    background-color: #ffffff;
    padding: 32px;
    border-radius: 12px;
    overflow-wrap: break-word;
}

.heading {
    margin: 0 0 12px 0;
    font-size: 20px;
    color: #111827;
}

.text {
    margin: 0 0 18px 0;
    color: #374151;
    line-height: 1.5;
}

.button-container {
    margin: 0 0 20px 0;
}

.button {
    display: inline-block;
    background-color: #3f2dd2;
    color: #ffffff !important;
    padding: 12px 24px;
    text-decoration: none;
    border-radius: 999px;
    font-weight: 500;
}

.muted {
    margin: 0 0 16px 0;
    color: #6b7280;
    font-size: 14px;
}

.link {
    color: #3f2dd2;
    text-decoration: none;
}

.footer {
    margin: 0;
    color: #374151;
}

.legal {
    margin: 20px 0 0 0;
    padding-top: 20px;
    border-top: 1px solid #eef2f6;
    font-size: 12px;
    color: #9ca3af;
}

.legal-link {
    color: #9ca3af;
    text-decoration: underline;
}

.copyright {
    margin: 12px 0 0 0;
    text-align: center;
    font-size: 12px;
    color: #9ca3af;
}

@media only screen and (max-width: 600px) {
    .email-container {
        padding: 24px 12px;
    }

    .email-content {
        padding: 24px;
    }
}
"""


def html_shell(content: str, locale: str, t: dict[str, str]) -> str:
    """Wrap already escaped notification content in the shared Kulturbytes layout."""
    return f'''<!DOCTYPE html>
<html lang="{escape(locale, quote=True)}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{EMAIL_CSS}</style>
</head>
<body>
<div class="email-container">
    <div class="email-content">
        {content}
        <p class="footer">
            {escape(t["signoff"])}<br/>
            <strong>{escape(t["team"])}</strong><br/><br/>
            <a href="https://kulturbytes.de" class="link">kulturbytes.de</a>
        </p>
        <div class="legal">
            <p style="margin:0 0 8px 0;">{escape(t["legal_address"])}</p>
            <p style="margin:0;">
                <a href="{escape(t["privacy_url"], quote=True)}" class="legal-link">
                    {escape(t["privacy_label"])}
                </a>
                &nbsp;|&nbsp;
                <a href="{escape(t["legal_url"], quote=True)}" class="legal-link">
                    {escape(t["legal_label"])}
                </a>
            </p>
        </div>
    </div>
    <p class="copyright">© DatenSindDaten e. V.</p>
</div>
</body>
</html>
'''


def safe_subject(value: str) -> str:
    return " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", value).split())[:180]


def render(
    payloads: list[NotificationPayload],
    requested: str,
    settings: Settings,
    ids: list[UUID] | None = None,
) -> NotificationPreview:
    if not payloads:
        raise ValueError("Empty email")
    locale, t = catalogue(requested)
    quality = payloads[0].rule is not None
    if any((p.rule is not None) != quality for p in payloads):
        raise ValueError("Mixed notification families")
    ranks = {"urgent": 0, "important": 1, "improvement": 2, "internal": 3}
    group_rank: dict[tuple[str, str], int] = {}
    for p in payloads:
        key = (p.entity_type, p.entity_key)
        group_rank[key] = min(group_rank.get(key, 3), ranks[p.priority])
    payloads = sorted(
        payloads,
        key=lambda p: (
            group_rank[(p.entity_type, p.entity_key)],
            p.entity_type,
            p.entity_name,
            p.entity_key,
            p.rule or "",
        ),
    )
    if quality:
        subject = t["quality_one" if len(payloads) == 1 else "quality_many"].format(
            count=len(payloads)
        )
    else:
        title = payloads[0].entity_name
        title = title if len(title) <= 90 else title[:87] + "…"
        subject = t["single" if len(payloads) == 1 else "multiple"].format(
            title=title, count=len(payloads)
        )
    plain = [t["hello"]]
    parts = [f'<h1 class="heading">{escape(t["hello"])}</h1>']

    def paragraph(value: str, *, muted: bool = False, strong: bool = False) -> None:
        plain.append(value)
        css_class = "muted" if muted else "text"
        content = escape(value)
        if strong:
            content = f"<strong>{content}</strong>"
        parts.append(f'<p class="{css_class}">{content}</p>')

    previous = None
    for p in payloads:
        group = (p.entity_type, p.entity_key)
        if group != previous:
            heading = f"{p.entity_name} · {t[p.entity_type]}"
            plain.append(heading)
            parts.append(f'<h2 class="heading">{escape(heading)}</h2>')
            previous = group
        if p.priority in {"urgent", "important"}:
            paragraph(t[p.priority], strong=True)
        if quality:
            policy = EXTERNAL_POLICY.get(p.rule or "")
            if policy is None or p.entity_type not in policy.entities:
                raise ValueError("Internal finding cannot be rendered externally")
            title = t[f"{policy.template}.title"]
            if p.rule == "url_syntax":
                title = t["link_title"].format(field=t.get(p.field or "", t["url"]))
            paragraph(title)
            paragraph(t[f"{policy.template}.explanation"].format(name=p.entity_name))
            paragraph(t[f"{policy.template}.recommendation"])
        else:
            if p.next_date is None or p.days_until is None or p.event_status is None:
                raise ValueError("Incomplete event snapshot")
            paragraph(
                t["intro"].format(
                    title=p.entity_name,
                    date=format_date(p.next_date, locale),
                    status=t[p.event_status],
                )
            )
            paragraph(
                t[
                    "today" if p.days_until == 0 else "tomorrow" if p.days_until == 1 else "days"
                ].format(count=p.days_until)
            )
            paragraph(t["publish"])
        action = recipient_action(p.external_action_url, p.entity_type, settings)
        if action is None:
            paragraph(t["action_guidance"])
        else:
            url, entity = action
            label = t[f"{entity}_action"]
            plain.append(f"{label}: {url}")
            escaped_url = escape(url, quote=True)
            parts.append(
                '<p class="button-container">'
                f'<a href="{escaped_url}" class="button" target="_blank" '
                f'rel="noopener noreferrer">{escape(label)}</a></p>'
            )
            parts.append(
                f'<p class="muted">{escape(t["button_fallback"])}<br/>'
                f'<a href="{escaped_url}" class="link" style="word-break:break-all;">'
                f"{escaped_url}</a></p>"
            )
    if not quality:
        paragraph(t["intentional"])
    paragraph(t["footer"].format(organization=payloads[0].organization_name), muted=True)
    plain.extend(
        [
            f"{t['signoff']}\n{t['team']}\n\nhttps://kulturbytes.de",
            t["legal_address"],
            f"{t['privacy_label']}: {t['privacy_url']}\n{t['legal_label']}: {t['legal_url']}",
            "© DatenSindDaten e. V.",
        ]
    )
    return NotificationPreview(
        subject=safe_subject(subject),
        text="\n\n".join(plain),
        html=html_shell("\n".join(parts), locale, t),
        locale=locale,
        notification_ids=ids or [],
        delivery_enabled=settings.notifications_delivery_enabled,
    )
