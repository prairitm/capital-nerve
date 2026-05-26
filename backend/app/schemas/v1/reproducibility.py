"""Phase 3 — analyst reproducibility export.

The reproducibility bundle is a self-contained JSON payload that lets an
analyst (or another LLM) re-derive a card's verdict offline:

- the **signal** that fired, with its rule text
- the **metric** that drove it, with formula and bounds
- the **inputs** that were resolved at run time, each anchored to a source
  page + extracted quote
- the **audit trail** (prompt / parser / model / seed) so the same run can
  be replayed from the extraction cache
- the **lineage graph** nodes/edges describing how
  ``ExtractedValue → FinancialStatementFact → CalculatedMetric → GeneratedSignal → IntelligenceCard``
  link together — the frontend renders this directly on the IO page.

Pure read-time view; nothing in this module mutates state.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class LineageNode(BaseModel):
    """One node in the extraction-to-card graph."""

    id: str  # type-prefixed primary key, e.g. ``extracted_value:42``
    kind: Literal[
        "extracted_value",
        "financial_fact",
        "calculated_metric",
        "generated_signal",
        "intelligence_card",
    ]
    label: str
    detail: str | None = None
    page_number: int | None = None
    document_id: int | None = None
    confidence_score: float | None = None
    validation_status: str | None = None  # validated | anomaly | quarantined


class LineageEdge(BaseModel):
    source: str  # node id
    target: str  # node id
    relationship: str  # extracted_to_fact | fact_to_metric | metric_to_signal | signal_to_card


class LineageGraph(BaseModel):
    nodes: list[LineageNode] = []
    edges: list[LineageEdge] = []


class ReproducibilityInput(BaseModel):
    """One resolved metric input, anchored to its source."""

    name: str
    code: str | None = None
    scope: str
    kind: str  # fact | metric
    value: float | None = None
    unit: str | None = None
    extracted_value_id: int | None = None
    page_number: int | None = None
    source_text: str | None = None
    confidence_score: float | None = None


class ReproducibilityMetric(BaseModel):
    metric_id: int | None = None
    code: str | None = None
    name: str | None = None
    metric_kind: str | None = None
    formula_text: str | None = None
    unit: str | None = None
    value: float | None = None
    validation_min: float | None = None
    validation_max: float | None = None
    is_quarantined: bool = False
    quarantine_reason: str | None = None
    anomaly_flag: bool = False
    anomaly_reason: str | None = None
    confidence_score: float | None = None
    inputs: list[ReproducibilityInput] = []


class ReproducibilitySignal(BaseModel):
    signal_id: int | None = None
    code: str | None = None
    name: str | None = None
    category: str | None = None
    rule_text: str | None = None
    direction: str | None = None
    severity: str | None = None
    confidence_score: float | None = None
    fired_value: float | None = None
    threshold: float | None = None
    operator: str | None = None
    explanation: str | None = None


class ReproducibilityAuditTrail(BaseModel):
    extraction_job_id: int | None = None
    prompt_version: str | None = None
    parser_version: str | None = None
    model_name: str | None = None
    provider_used: str | None = None
    llm_temperature: float | None = None
    llm_seed: int | None = None
    request_hash: str | None = None
    completed_at: datetime | None = None
    reprocess_timestamp: datetime | None = None


class ReproducibilityCard(BaseModel):
    card_id: int
    card_type: str
    headline: str
    one_line_summary: str | None = None
    direction: str | None = None
    severity: str | None = None
    confidence_score: float | None = None
    is_published: bool


class ReproducibilityBundle(BaseModel):
    """Top-level export shape — one analyst-ready JSON document per card."""

    card: ReproducibilityCard
    signal: ReproducibilitySignal | None = None
    metric: ReproducibilityMetric | None = None
    audit_trail: ReproducibilityAuditTrail | None = None
    lineage: LineageGraph
    exported_at: datetime
