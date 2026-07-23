from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from monitor.notifications import PermanentNotificationError, render_email, send_email


class NotificationTemplateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "analytics.db"
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE companies (id TEXT PRIMARY KEY, name TEXT, ticker TEXT);
            CREATE TABLE events (id TEXT PRIMARY KEY, company_id TEXT, event_type TEXT, event_date TEXT, title TEXT);
            CREATE TABLE signals (signal_id TEXT PRIMARY KEY, event_id TEXT, signal_code TEXT, severity TEXT, direction TEXT);
            INSERT INTO companies VALUES ('company', 'Alpha & Sons', 'ALPHA');
            INSERT INTO events VALUES ('event', 'company', 'Financial Results', '2026-07-18', '<Strong> Results');
            INSERT INTO signals VALUES ('signal', 'event', 'revenue_growth', 'HIGH', 'POSITIVE');
            """
        )
        conn.close()
        self.settings = SimpleNamespace(
            analytics_db_path=self.db_path,
            public_app_url="https://www.capitalnerve.com",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="capitalnerve@gmail.com",
            smtp_password="app-password",
            email_from_address="capitalnerve@gmail.com",
            email_from_name="CapitalNerve",
            smtp_timeout_seconds=30,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_watchlist_email_has_plain_html_links_and_escaped_content(self) -> None:
        subject, plain, html = render_email(
            self.settings,
            {
                "message_kind": "watchlist_update",
                "event_id": "event",
                "action_token": "unsubscribe-token",
            },
        )
        self.assertIn("ALPHA", subject)
        self.assertIn("Revenue Growth", plain)
        self.assertIn("/company/ALPHA/event/event", plain)
        self.assertIn("Alpha &amp; Sons", html)
        self.assertIn("&lt;Strong&gt; Results", html)
        self.assertNotIn("<Strong> Results", html)

    def test_smtp_uses_starttls_login_and_multipart_message(self) -> None:
        item = {"message_kind": "test_email", "recipient_email": "user@example.com"}
        with patch("monitor.notifications.smtplib.SMTP") as smtp_type:
            provider_id = send_email(self.settings, item)
        smtp = smtp_type.return_value.__enter__.return_value
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("capitalnerve@gmail.com", "app-password")
        message = smtp.send_message.call_args.args[0]
        self.assertTrue(message.is_multipart())
        self.assertEqual("user@example.com", message["To"])
        self.assertIn("@gmail.com", provider_id)

    def test_missing_smtp_password_is_a_permanent_failure(self) -> None:
        self.settings.smtp_password = ""
        with self.assertRaises(PermanentNotificationError):
            send_email(
                self.settings,
                {"message_kind": "test_email", "recipient_email": "user@example.com"},
            )


if __name__ == "__main__":
    unittest.main()
