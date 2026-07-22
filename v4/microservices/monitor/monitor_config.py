from __future__ import annotations

import os
from pathlib import Path


MONITOR_DIR = Path(__file__).resolve().parent
V4_DIR = MONITOR_DIR.parent.parent


class Settings:
    def __init__(self) -> None:
        data_dir = V4_DIR / "data"
        self.app_db_path = Path(
            os.getenv("MONITOR_APP_DB_PATH", os.getenv("V4_APP_DB_PATH", str(data_dir / "capital_nerve_app.db")))
        ).resolve()
        self.analytics_db_path = Path(
            os.getenv("MONITOR_ANALYTICS_DB_PATH", os.getenv("V4_DB_PATH", str(data_dir / "capital_nerve.db")))
        ).resolve()
        self.poll_interval_seconds = int(os.getenv("MONITOR_POLL_INTERVAL_SECONDS", "120"))
        self.poll_lease_seconds = int(os.getenv("MONITOR_POLL_LEASE_SECONDS", "60"))
        self.job_lease_seconds = int(os.getenv("MONITOR_JOB_LEASE_SECONDS", "180"))
        self.max_attempts = int(os.getenv("MONITOR_MAX_ATTEMPTS", "5"))
        self.pipeline_version = os.getenv("MONITOR_PIPELINE_VERSION", "v4-1")
        self.flow_timeout_seconds = float(os.getenv("MONITOR_FLOW_TIMEOUT_SECONDS", "1800"))
        self.smtp_host = os.getenv("V4_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("V4_SMTP_PORT", "587"))
        self.smtp_username = os.getenv("V4_SMTP_USERNAME", "capitalnerve@gmail.com")
        self.smtp_password = os.getenv("V4_SMTP_PASSWORD", "").replace(" ", "")
        self.email_from_address = os.getenv("V4_EMAIL_FROM_ADDRESS", "capitalnerve@gmail.com")
        self.email_from_name = os.getenv("V4_EMAIL_FROM_NAME", "CapitalNerve")
        self.public_app_url = os.getenv(
            "V4_PUBLIC_APP_URL", "https://capital-nerve.taildeaa7c.ts.net"
        ).rstrip("/")
        self.email_max_attempts = int(os.getenv("V4_EMAIL_MAX_ATTEMPTS", "5"))
        self.email_lease_seconds = int(os.getenv("V4_EMAIL_LEASE_SECONDS", "120"))
        self.email_worker_interval_seconds = float(os.getenv("V4_EMAIL_WORKER_INTERVAL_SECONDS", "2"))
        self.review_reconciliation_interval_seconds = float(
            os.getenv("MONITOR_REVIEW_RECONCILIATION_INTERVAL_SECONDS", "5")
        )
        self.smtp_timeout_seconds = float(os.getenv("V4_SMTP_TIMEOUT_SECONDS", "30"))
        self.service_urls = {
            "company": os.getenv("MONITOR_COMPANY_URL", "http://127.0.0.1:8020"),
            "event": os.getenv("MONITOR_EVENT_URL", "http://127.0.0.1:8021"),
            "event_type": os.getenv("MONITOR_EVENT_TYPE_URL", "http://127.0.0.1:8022"),
            "values": os.getenv("MONITOR_VALUES_URL", "http://127.0.0.1:8023"),
            "metrics": os.getenv("MONITOR_METRICS_URL", "http://127.0.0.1:8024"),
            "signals": os.getenv("MONITOR_SIGNALS_URL", "http://127.0.0.1:8025"),
            "alerts": os.getenv("MONITOR_ALERTS_URL", "http://127.0.0.1:8026"),
        }


settings = Settings()
