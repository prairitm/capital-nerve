"""v1 metric-registry schemas.

The registry exposes the metric ontology to the frontend so the analyst-trust
strip (`MetricKindBadge`, `TriggerMetricStrip`) and the new
`MetricRegistryDrawer` can render the same definition the pipeline computed
against — formula, expected range, inputs, related signals.

The shape mirrors :class:`app.models.intelligence.MetricDefinition` plus a
hand-trimmed list of the signal codes that consume the metric.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


MetricKindLiteral = Literal["financial", "model_score", "composite"]


class MetricRegistryInput(BaseModel):
    """One declared input feeding a metric formula."""

    name: str
    code: str | None = None
    scope: str
    kind: str


class MetricRegistrySignal(BaseModel):
    """A signal that fires off this metric."""

    signal_code: str
    signal_name: str
    rule_text: str | None = None


class MetricRegistryEntry(BaseModel):
    """Public-facing definition of a metric in the registry."""

    metric_code: str
    metric_name: str
    metric_category: str
    metric_kind: MetricKindLiteral
    unit: str | None = None
    formula_text: str | None = None
    is_percentage: bool
    is_bps: bool
    validation_min: float | None = None
    validation_max: float | None = None
    inputs: list[MetricRegistryInput] = []
    dependencies: list[str] = []
    related_signals: list[MetricRegistrySignal] = []


class MetricRegistryResponse(BaseModel):
    """List wrapper so the response shape is stable when we add metadata."""

    metrics: list[MetricRegistryEntry]
