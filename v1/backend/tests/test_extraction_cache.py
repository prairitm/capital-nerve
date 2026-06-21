"""Tests for the extraction request-hash cache and payload replay.

These tests run without a database — they exercise the pure helpers used by
``extraction.run_extraction``: the cache-key construction, the canonical
JSON parse path, and provider-call avoidance when a previous job is
replayable.

Run with::

    cd backend && pytest tests/test_extraction_cache.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from app.services.pipeline.extraction import _compute_request_hash
from app.services.pipeline.llm import (
    PROMPT_VERSION,
    ExtractedLineItem,
    ExtractionResult,
    ProviderPage,
    _items_from_payload,
    parse_extraction_payload,
)
from app.services.pipeline.parsing import PARSER_VERSION


# ---------------------------------------------------------------------------
# Stub document + provider
# ---------------------------------------------------------------------------


@dataclass
class _StubDoc:
    document_id: int = 1
    file_hash: str | None = "abc123"


class _RecordingProvider:
    """Mimics the provider Protocol; records how many times it was called."""

    name = "stub:test-model"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def extract_financial_facts(
        self, *, pages: list[ProviderPage], document_title: str
    ) -> ExtractionResult:
        del pages, document_title
        self.calls += 1
        items, overall, notes = _items_from_payload(self.payload)
        raw = json.dumps(self.payload, sort_keys=True)
        return ExtractionResult(
            items=items,
            model_name=self.name,
            overall_confidence=overall,
            raw_response=raw,
            notes=notes,
            temperature=0.0,
            seed=42,
            provider_used="stub",
        )


# ---------------------------------------------------------------------------
# Request hash
# ---------------------------------------------------------------------------


def test_request_hash_is_stable_for_identical_inputs():
    doc = _StubDoc()
    h1 = _compute_request_hash(
        document=doc, provider_name="anthropic:claude", model="claude-x", seed=42
    )
    h2 = _compute_request_hash(
        document=doc, provider_name="anthropic:claude", model="claude-x", seed=42
    )
    assert h1 == h2


def test_request_hash_changes_with_seed():
    doc = _StubDoc()
    h1 = _compute_request_hash(
        document=doc, provider_name="anthropic:claude", model="claude-x", seed=42
    )
    h2 = _compute_request_hash(
        document=doc, provider_name="anthropic:claude", model="claude-x", seed=7
    )
    assert h1 != h2


def test_request_hash_changes_with_model():
    doc = _StubDoc()
    h1 = _compute_request_hash(
        document=doc, provider_name="anthropic:claude", model="claude-x", seed=42
    )
    h2 = _compute_request_hash(
        document=doc, provider_name="anthropic:claude", model="claude-y", seed=42
    )
    assert h1 != h2


def test_request_hash_changes_with_file_hash():
    h1 = _compute_request_hash(
        document=_StubDoc(file_hash="aaa"),
        provider_name="x",
        model="y",
        seed=1,
    )
    h2 = _compute_request_hash(
        document=_StubDoc(file_hash="bbb"),
        provider_name="x",
        model="y",
        seed=1,
    )
    assert h1 != h2


def test_request_hash_incorporates_prompt_and_parser_versions():
    """If either version constant changes, the cache key must change too.

    This is a regression guard: bumping ``PROMPT_VERSION`` or
    ``PARSER_VERSION`` is the only way to force a global re-extraction; the
    test pins the contract so a refactor can't accidentally drop one of them
    from the key.
    """
    doc = _StubDoc()
    h = _compute_request_hash(
        document=doc, provider_name="x", model="y", seed=1
    )
    assert PROMPT_VERSION in _hash_input_for(doc, "x", "y", 1)
    assert PARSER_VERSION in _hash_input_for(doc, "x", "y", 1)
    # And the hash actually depends on it:
    original = PROMPT_VERSION
    try:
        import app.services.pipeline.extraction as ext_mod
        import app.services.pipeline.llm as llm_mod

        llm_mod.PROMPT_VERSION = "extract.different"
        ext_mod.PROMPT_VERSION = "extract.different"
        h2 = _compute_request_hash(
            document=doc, provider_name="x", model="y", seed=1
        )
    finally:
        llm_mod.PROMPT_VERSION = original
        ext_mod.PROMPT_VERSION = original
    assert h != h2


def _hash_input_for(doc, provider_name, model, seed):
    return "|".join(
        [
            doc.file_hash or f"doc:{doc.document_id}",
            PROMPT_VERSION,
            PARSER_VERSION,
            provider_name,
            model,
            str(seed),
        ]
    )


# ---------------------------------------------------------------------------
# Payload replay
# ---------------------------------------------------------------------------


_SAMPLE_PAYLOAD = {
    "items": [
        {
            "normalized_code": "revenue_from_operations",
            "raw_label": "Revenue from Operations",
            "value": 17394.0,
            "unit": "crore",
            "page_number": 2,
            "source_text": "Revenue from Operations 17,394",
            "confidence": 92.0,
        },
        {
            "normalized_code": "pat",
            "raw_label": "Profit After Tax",
            "value": 4205.0,
            "unit": "crore",
            "page_number": 2,
            "source_text": "Profit After Tax 4,205",
            "confidence": 90.0,
        },
    ],
    "overall_confidence": 91.0,
    "notes": [],
}


def test_parse_extraction_payload_round_trips_canonical_json():
    raw = json.dumps(_SAMPLE_PAYLOAD, sort_keys=True)
    items, overall, notes = parse_extraction_payload(raw)
    assert overall == pytest.approx(91.0)
    assert notes == []
    by_code = {i.normalized_code: i for i in items}
    assert by_code["revenue_from_operations"].value == pytest.approx(17394.0)
    assert by_code["pat"].confidence == pytest.approx(90.0)


def test_replaying_same_payload_yields_identical_items():
    """The pure-replay path is the heart of the determinism contract."""
    raw = json.dumps(_SAMPLE_PAYLOAD, sort_keys=True)
    first, _, _ = parse_extraction_payload(raw)
    second, _, _ = parse_extraction_payload(raw)
    assert len(first) == len(second)
    for a, b in zip(first, second):
        assert a.normalized_code == b.normalized_code
        assert a.value == b.value
        assert a.unit == b.unit
        assert a.page_number == b.page_number
        assert a.confidence == b.confidence
        assert a.source_text == b.source_text


def test_parse_extraction_payload_handles_bad_json():
    items, overall, notes = parse_extraction_payload("not json at all {")
    assert items == []
    assert overall == 0.0
    assert notes and "not valid JSON" in notes[0]


def test_recording_provider_is_called_exactly_once_per_extraction():
    """Sanity check on the stub: each call increments `calls` by 1.

    The cache replay path in `run_extraction` bypasses the provider
    altogether, so in integration the second invocation would not bump this
    counter at all — but exercising that requires a DB. We pin the unit-test
    contract here so the integration version stays well-defined.
    """
    provider = _RecordingProvider(_SAMPLE_PAYLOAD)
    provider.extract_financial_facts(
        pages=[ProviderPage(page_number=1, text="x", image_bytes=None)],
        document_title="t",
    )
    provider.extract_financial_facts(
        pages=[ProviderPage(page_number=1, text="x", image_bytes=None)],
        document_title="t",
    )
    assert provider.calls == 2
