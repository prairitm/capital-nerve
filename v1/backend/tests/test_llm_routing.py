"""Routing helpers for the LLM provider.

Covers:

- `select_extraction_model(document)` — per-document-type fast lane that
  routes transcripts / press releases / presentations / annual reports
  through `LLM_MODEL_FAST` while keeping `FINANCIAL_RESULT` on `LLM_MODEL`.
- Anthropic prompt-cache breakpoints — the system prompt and tool schema
  the extraction request sends MUST carry `cache_control: ephemeral`
  markers so repeated calls hit Anthropic's prompt cache.

Run with::

    cd backend && pytest tests/test_llm_routing.py
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.db.enums import DocumentType
from app.services.pipeline.llm import (
    _ANTHROPIC_TOOL,
    _EXTRACTION_SYSTEM_PROMPT,
    _RAG_SYSTEM_PROMPT,
    _cached_anthropic_system,
    _cached_anthropic_tools,
    select_extraction_model,
)


@dataclass
class _StubDoc:
    document_type: DocumentType


# ---------------------------------------------------------------------------
# select_extraction_model
# ---------------------------------------------------------------------------


def test_fast_model_unset_routes_everything_to_premium(monkeypatch):
    monkeypatch.setattr("app.services.pipeline.llm.settings.LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setattr("app.services.pipeline.llm.settings.LLM_MODEL_FAST", None)
    for doc_type in DocumentType:
        assert select_extraction_model(_StubDoc(doc_type)) == "claude-sonnet-4-6"


def test_fast_model_routes_transcripts_and_announcements(monkeypatch):
    monkeypatch.setattr("app.services.pipeline.llm.settings.LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setattr(
        "app.services.pipeline.llm.settings.LLM_MODEL_FAST", "claude-haiku-4-5"
    )
    fast_types = {
        DocumentType.CONCALL_TRANSCRIPT,
        DocumentType.INVESTOR_PRESENTATION,
        DocumentType.PRESS_RELEASE,
        DocumentType.ANNUAL_REPORT,
    }
    for doc_type in fast_types:
        assert select_extraction_model(_StubDoc(doc_type)) == "claude-haiku-4-5"


def test_financial_result_always_uses_premium(monkeypatch):
    monkeypatch.setattr("app.services.pipeline.llm.settings.LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setattr(
        "app.services.pipeline.llm.settings.LLM_MODEL_FAST", "claude-haiku-4-5"
    )
    assert (
        select_extraction_model(_StubDoc(DocumentType.FINANCIAL_RESULT))
        == "claude-sonnet-4-6"
    )


def test_empty_string_fast_model_treated_as_unset(monkeypatch):
    monkeypatch.setattr("app.services.pipeline.llm.settings.LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setattr("app.services.pipeline.llm.settings.LLM_MODEL_FAST", "   ")
    assert (
        select_extraction_model(_StubDoc(DocumentType.CONCALL_TRANSCRIPT))
        == "claude-sonnet-4-6"
    )


# ---------------------------------------------------------------------------
# Prompt-cache breakpoints
# ---------------------------------------------------------------------------


def test_cached_system_prompt_carries_breakpoint():
    blocks = _cached_anthropic_system(_EXTRACTION_SYSTEM_PROMPT)
    assert isinstance(blocks, list) and len(blocks) == 1
    block = blocks[0]
    assert block["type"] == "text"
    assert block["text"] == _EXTRACTION_SYSTEM_PROMPT
    assert block["cache_control"] == {"type": "ephemeral"}


def test_cached_rag_system_prompt_carries_breakpoint():
    blocks = _cached_anthropic_system(_RAG_SYSTEM_PROMPT)
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_cached_tools_apply_breakpoint_to_last_tool():
    tools = _cached_anthropic_tools(_ANTHROPIC_TOOL)
    assert len(tools) == 1
    tool = tools[0]
    assert tool["name"] == _ANTHROPIC_TOOL["name"]
    assert tool["input_schema"] is _ANTHROPIC_TOOL["input_schema"]
    assert tool["cache_control"] == {"type": "ephemeral"}


def test_cached_tools_does_not_mutate_source_dict():
    """Ensure the module-level tool dict stays clean for downstream callers."""
    _ = _cached_anthropic_tools(_ANTHROPIC_TOOL)
    assert "cache_control" not in _ANTHROPIC_TOOL
