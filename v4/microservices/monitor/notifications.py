"""Email rendering and Gmail SMTP delivery for durable outbox messages."""

from __future__ import annotations

import html
import smtplib
import sqlite3
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any
from urllib.parse import quote

from .monitor_config import Settings


class PermanentNotificationError(RuntimeError):
    pass


def _signal_label(code: str) -> str:
    return code.replace("_", " ").strip().title()


def _watchlist_context(settings: Settings, item: dict[str, Any]) -> dict[str, Any]:
    uri = f"file:{settings.analytics_db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT e.id, e.event_type, e.event_date, e.title,
                   c.name AS company_name, c.ticker
            FROM events e JOIN companies c ON c.id = e.company_id
            WHERE e.id = ?
            """,
            (item["event_id"],),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Event {item['event_id']} is not available for email rendering")
        signals = conn.execute(
            """
            SELECT signal_code, severity, direction FROM signals WHERE event_id = ?
            ORDER BY CASE UPPER(COALESCE(severity, ''))
                WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2
                WHEN 'LOW' THEN 3 ELSE 9 END, signal_code
            LIMIT 3
            """,
            (item["event_id"],),
        ).fetchall()
    finally:
        conn.close()
    return {**dict(row), "signals": [dict(signal) for signal in signals]}


def render_email(settings: Settings, item: dict[str, Any]) -> tuple[str, str, str]:
    app_url = settings.public_app_url
    kind = item["message_kind"]
    if kind == "test_email":
        subject = "Your CapitalNerve email alerts are ready"
        text = (
            "This is a test email from CapitalNerve.\n\n"
            "Your notification address is working. New updates for companies on your "
            f"watchlist will appear here.\n\nManage alerts: {app_url}/profile"
        )
        body = """
            <h1 style="font-size:22px;margin:0 0 16px">Your email alerts are ready</h1>
            <p>This is a test email from CapitalNerve. Your notification address is working.</p>
            <p>New updates for companies on your watchlist will appear here.</p>
        """
        html_body = _frame(body, f"{app_url}/profile", "Manage alerts")
        return subject, text, html_body
    if kind == "verify_email":
        token = quote(str(item["action_token"]), safe="")
        verify_url = f"{app_url}/api/notifications/verify?token={token}"
        subject = "Verify your CapitalNerve notification email"
        text = (
            "Verify this address to receive CapitalNerve watchlist alerts.\n\n"
            f"Verify email: {verify_url}\n\nThis link expires in 24 hours."
        )
        body = """
            <h1 style="font-size:22px;margin:0 0 16px">Verify your notification email</h1>
            <p>Confirm this address to receive new watchlist updates from CapitalNerve.</p>
            <p style="color:#64748b;font-size:13px">This link expires in 24 hours.</p>
        """
        return subject, text, _frame(body, verify_url, "Verify email")
    if kind != "watchlist_update":
        raise PermanentNotificationError(f"Unknown email kind: {kind}")

    context = _watchlist_context(settings, item)
    company = context["company_name"] or context["ticker"] or "Watchlist company"
    ticker = context["ticker"] or ""
    title = context["title"] or context["event_type"] or "New filing"
    event_url = f"{app_url}/company/{quote(ticker, safe='')}/event/{quote(context['id'], safe='')}"
    unsubscribe_url = (
        f"{app_url}/api/notifications/unsubscribe?token="
        f"{quote(str(item['action_token']), safe='')}"
    )
    subject = f"{ticker}: New {context['event_type']}" if ticker else f"New update from {company}"
    signal_lines = [
        f"- {_signal_label(signal['signal_code'])} ({signal['severity'] or 'Unrated'})"
        for signal in context["signals"]
    ]
    signals_text = "\n".join(signal_lines) if signal_lines else "No headline signals were triggered."
    text = (
        f"{company}{f' ({ticker})' if ticker else ''}\n"
        f"{title}\nPublished: {context['event_date']}\n\n"
        f"Key signals\n{signals_text}\n\nView update: {event_url}\n"
        f"Manage alerts: {app_url}/profile\nUnsubscribe: {unsubscribe_url}"
    )
    if context["signals"]:
        items = "".join(
            f"<li style='margin:8px 0'><strong>{html.escape(_signal_label(signal['signal_code']))}</strong> "
            f"<span style='color:#64748b'>({html.escape(signal['severity'] or 'Unrated')})</span></li>"
            for signal in context["signals"]
        )
        signals_html = f"<h2 style='font-size:16px;margin:24px 0 8px'>Key signals</h2><ul>{items}</ul>"
    else:
        signals_html = "<p style='color:#64748b'>No headline signals were triggered.</p>"
    body = (
        f"<p style='color:#3b82f6;font-weight:600;margin:0 0 8px'>{html.escape(context['event_type'])}</p>"
        f"<h1 style='font-size:22px;margin:0 0 12px'>{html.escape(company)}"
        f"{f' ({html.escape(ticker)})' if ticker else ''}</h1>"
        f"<p style='font-size:17px'>{html.escape(title)}</p>"
        f"<p style='color:#64748b;font-size:13px'>Published {html.escape(context['event_date'])}</p>"
        f"{signals_html}"
    )
    footer = (
        f"<a href='{html.escape(app_url + '/profile', quote=True)}'>Manage alerts</a> · "
        f"<a href='{html.escape(unsubscribe_url, quote=True)}'>Unsubscribe</a>"
    )
    return subject, text, _frame(body, event_url, "View update", footer)


def _frame(body: str, action_url: str, action_label: str, footer: str | None = None) -> str:
    footer_html = footer or "You are receiving this because you enabled CapitalNerve email alerts."
    return f"""<!doctype html><html><body style="margin:0;background:#f4f7fb;font-family:Arial,sans-serif;color:#172033">
    <div style="max-width:600px;margin:0 auto;padding:28px 16px">
      <div style="background:#fff;border:1px solid #dfe5ee;border-radius:14px;padding:28px">
        <div style="font-weight:700;margin-bottom:24px">CapitalNerve</div>
        {body}
        <p style="margin:28px 0"><a href="{html.escape(action_url, quote=True)}" style="background:#2563eb;color:#fff;text-decoration:none;padding:12px 18px;border-radius:9px;display:inline-block">{html.escape(action_label)}</a></p>
      </div>
      <div style="color:#64748b;font-size:12px;text-align:center;padding:18px">{footer_html}</div>
    </div></body></html>"""


def send_email(settings: Settings, item: dict[str, Any]) -> str:
    if not settings.smtp_password:
        raise PermanentNotificationError("V4_SMTP_PASSWORD is not configured")
    subject, plain_text, html_text = render_email(settings, item)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((settings.email_from_name, settings.email_from_address))
    message["To"] = item["recipient_email"]
    message["Message-ID"] = make_msgid(domain=settings.email_from_address.split("@")[-1])
    message.set_content(plain_text)
    message.add_alternative(html_text, subtype="html")
    try:
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
        ) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused) as exc:
        raise PermanentNotificationError(str(exc)) from exc
    return str(message["Message-ID"])
