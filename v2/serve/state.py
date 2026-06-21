"""Process-local state for the serving layer.

The v2 store is read-only intelligence data; user-facing mutable state (auth,
watchlist, watch items, ingest jobs, admin-added companies) lives here in
memory. It resets on restart, which is appropriate for this serving shim.
"""

from __future__ import annotations

import hashlib
import hmac
import itertools
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import settings

_PBKDF2_ROUNDS = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return hmac.compare_digest(expected.hex(), digest_hex)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class User:
    user_id: int
    email: str
    full_name: str | None
    hashed_password: str
    user_type: str = "ANALYST"
    watchlist_company_ids: set[int] = field(default_factory=set)


class Store:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.users_by_id: dict[int, User] = {}
        self._user_seq = itertools.count(1)
        self.watch_items: list[dict[str, Any]] = []
        self._watch_item_seq = itertools.count(1)
        self.ingest_jobs: list[dict[str, Any]] = []
        self._job_seq = itertools.count(1)
        self.extra_companies: list[dict[str, Any]] = []
        self.read_alerts: set[int] = set()
        self._bootstrap_dev_user()

    def _bootstrap_dev_user(self) -> None:
        if settings.dev_email and settings.dev_password:
            self.create_user(settings.dev_email, settings.dev_password, "Dev User", "ADMIN")

    # -------------------------------------------------------------- users
    def create_user(self, email: str, password: str, full_name: str | None, user_type: str = "ANALYST") -> User:
        if email in self.users:
            return self.users[email]
        user = User(
            user_id=next(self._user_seq),
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            user_type=user_type,
        )
        self.users[email] = user
        self.users_by_id[user.user_id] = user
        return user

    def verify(self, email: str, password: str) -> User | None:
        user = self.users.get(email)
        if user and verify_password(password, user.hashed_password):
            return user
        return None

    # --------------------------------------------------------- watch items
    def add_watch_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = {
            "watch_item_id": next(self._watch_item_seq),
            "created_at": _now(),
            "is_active": True,
            "condition_json": {},
            **payload,
        }
        self.watch_items.append(item)
        return item

    def remove_watch_item(self, watch_item_id: int) -> bool:
        before = len(self.watch_items)
        self.watch_items = [w for w in self.watch_items if w["watch_item_id"] != watch_item_id]
        return len(self.watch_items) != before

    # -------------------------------------------------------- ingest jobs
    def add_ingest_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = {
            "job_id": next(self._job_seq),
            "created_at": _now(),
            "status": "PENDING",
            **payload,
        }
        self.ingest_jobs.append(job)
        return job


store = Store()
