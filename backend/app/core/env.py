"""Environment bootstrap for standalone CLIs and the IR-discovery agent.

Pydantic ``Settings`` reads ``backend/.env`` into field values but does **not**
export them to ``os.environ``. The OpenAI Agents SDK (and the ``openai``
client it constructs) only checks ``os.environ["OPENAI_API_KEY"]``, so a
key that exists only in ``.env`` looks "missing" unless we bridge it.

Call :func:`bootstrap_cli_env` at the top of any ``python -m app.scripts.*``
entry point, and :func:`ensure_openai_api_key` immediately before the first
Agents SDK ``Runner.run``.
"""
from __future__ import annotations

import os
from pathlib import Path

# backend/app/core/env.py -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_ROOT / ".env"


def bootstrap_cli_env() -> None:
    """Load ``backend/.env`` into ``os.environ`` (no overwrite of existing vars)."""
    if not _ENV_FILE.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        # pydantic-settings can still read the file for Settings fields.
        return
    load_dotenv(_ENV_FILE, override=False)


def ensure_openai_api_key() -> str:
    """Return a non-empty OpenAI API key, syncing from Settings when needed.

    Raises ``RuntimeError`` with an actionable message when the key is
    absent from both ``os.environ`` and ``settings.OPENAI_API_KEY``.
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key

    # Import here so bootstrap_cli_env() can run before Settings is first used.
    from app.core.config import settings

    key = (settings.OPENAI_API_KEY or "").strip()
    if key:
        os.environ["OPENAI_API_KEY"] = key
        return key

    raise RuntimeError(
        "OPENAI_API_KEY is required for IR discovery. Set it in backend/.env "
        "(see backend/.env.example) or export it in your shell before running "
        "python -m app.scripts.bulk_ingest."
    )


__all__ = ["bootstrap_cli_env", "ensure_openai_api_key", "_ENV_FILE"]
