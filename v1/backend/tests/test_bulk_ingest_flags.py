"""CLI-flag-level tests for `app.scripts.bulk_ingest`.

These tests use Typer's `CliRunner` and stop at flag-handling so they
don't touch the DB or hit any external API. They lock in:

- `--no-agent-fallback` and `--agent-only` are mutually exclusive.
- `--agent-only` keeps the OpenAI-key precondition active.
- `--no-agent-fallback` skips the OpenAI-key precondition.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from app.scripts.bulk_ingest import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_no_agent_fallback_and_agent_only_are_mutually_exclusive(
    runner: CliRunner,
) -> None:
    result = runner.invoke(
        app,
        [
            "--symbols", "RELIANCE",
            "--from", "Q3 FY25-26",
            "--to", "Q3 FY25-26",
            "--no-agent-fallback",
            "--agent-only",
            "--dry-run",
        ],
    )
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_agent_only_still_requires_openai_api_key(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--agent-only` *requires* the agent path, so the OPENAI_API_KEY
    precondition must still fire when neither env var nor settings has
    one."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.core.config.settings",
        SimpleNamespace(OPENAI_API_KEY=None, IR_AGENT_CONCURRENCY=1),
    )

    result = runner.invoke(
        app,
        [
            "--symbols", "RELIANCE",
            "--from", "Q3 FY25-26",
            "--to", "Q3 FY25-26",
            "--agent-only",
            "--dry-run",
        ],
    )
    assert result.exit_code == 2
    assert "OPENAI_API_KEY" in result.output


def test_no_agent_fallback_skips_openai_key_check(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--no-agent-fallback` lets the run start without an OpenAI key.
    We don't drive the run to completion (no admin user / no real DB);
    we just verify the key precondition isn't what stopped us."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = runner.invoke(
        app,
        [
            "--symbols", "DOES_NOT_EXIST_TICKER",
            "--from", "Q3 FY25-26",
            "--to", "Q3 FY25-26",
            "--no-agent-fallback",
            "--dry-run",
        ],
    )
    # The CLI may exit non-zero for downstream reasons (e.g. no
    # matching companies), but the failure must NOT be the OPENAI_API_KEY
    # precondition.
    assert "OPENAI_API_KEY" not in result.output
