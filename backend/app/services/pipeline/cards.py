"""Stage 5: `GeneratedSignal` → `IntelligenceCard` + `CardEvidence`.

This is the layer the user finally sees on Home, Company, and the drawer.
Cards materialize evidence from `ExtractedValue` and `CalculatedMetric` so the
"Evidence" panel in the drawer always points back at a real source line and a
documented calculation step.

For `QUARTERLY_RESULT` events we also synthesize a single `result_verdict`
card that summarises the quarter. The verdict is not tied to one signal —
it aggregates the strongest signals and the headline metrics, which is why
its `signal_id` is left as ``None`` and the frontend treats `result_verdict`
as a recognised summary type rather than a generic signal card.
"""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.enums import (
    ConfidenceLevel,
    EventType,
    SeverityLevel,
    SignalDirection,
)
from app.models.events import CompanyEvent, SourceDocument
from app.models.facts import ExtractedValue
from app.models.intelligence import (
    CalculatedMetric,
    CardEvidence,
    GeneratedSignal,
    IntelligenceCard,
    MetricDefinition,
    SignalDefinition,
)

logger = logging.getLogger(__name__)


# Signal category → card_type used by the UI badges + colours.
# Card type strings are free-form on `IntelligenceCard.card_type`; the frontend
# treats unknown variants the same as `signal`. Keep this map exhaustive so the
# right colour bucket and copy template fire for every category produced by
# `signal_definitions.signal_category`.
_CATEGORY_TO_CARD_TYPE: dict[str, str] = {
    "margin": "margin_movement",
    "growth": "growth_signal",
    "profit_quality": "profit_quality",
    "earnings_quality": "earnings_quality",
    "expense": "cost_pressure",
    "debt": "debt_signal",
    "solvency": "solvency_signal",
    "red_flag": "red_flag",
    "management": "management_signal",
    "management_tone": "management_tone",
    "cashflow": "cashflow_signal",
    "cash_quality": "cash_quality",
    "working_capital": "working_capital",
    "valuation": "valuation_signal",
    "market_reaction": "market_reaction",
    "governance": "governance_signal",
    "guidance": "guidance_signal",
    "order_book": "order_book",
}


def run_cards(
    db: Session,
    *,
    document: SourceDocument,
    signals: Iterable[GeneratedSignal],
    publish: bool,
) -> list[IntelligenceCard]:
    """Materialize one card per published signal.

    `publish` controls `is_published`; the runner flips this based on the
    document's overall extraction confidence vs `AUTO_PUBLISH_CONFIDENCE`.
    """
    # Re-runs replace previous cards for this document.
    existing_card_ids = list(
        db.execute(
            select(IntelligenceCard.card_id).where(
                IntelligenceCard.document_id == document.document_id
            )
        ).scalars()
    )
    if existing_card_ids:
        db.execute(
            delete(CardEvidence).where(CardEvidence.card_id.in_(existing_card_ids))
        )
        db.execute(
            delete(IntelligenceCard).where(IntelligenceCard.card_id.in_(existing_card_ids))
        )

    # Pre-load metric + signal-def context for the cards we're about to write.
    extracted_by_code = _extracted_by_code(db, document.document_id)

    written: list[IntelligenceCard] = []
    for sig in signals:
        sd = db.get(SignalDefinition, sig.signal_def_id)
        if not sd:
            continue
        cm = db.get(CalculatedMetric, sig.primary_metric_id) if sig.primary_metric_id else None
        md = db.get(MetricDefinition, cm.metric_def_id) if cm else None
        metrics_json = _metrics_json_for(cm, md)
        calculations_json = _calculations_json_for(cm)

        card = IntelligenceCard(
            company_id=document.company_id,
            event_id=document.event_id,
            document_id=document.document_id,
            period_id=document.period_id,
            signal_id=sig.signal_id,
            card_type=_CATEGORY_TO_CARD_TYPE.get(sd.signal_category, "signal"),
            card_priority=_card_priority(sig),
            headline=sig.headline or sd.signal_name,
            one_line_summary=_one_liner(sig, cm, md),
            detailed_explanation=sig.explanation,
            signal_direction=sig.signal_direction,
            severity=sig.severity,
            confidence_score=sig.confidence_score,
            confidence_level=_confidence_to_level(float(sig.confidence_score or 0)),
            investor_question=_investor_question(sd, sig.signal_direction),
            watch_next=_watch_next(sd, sig.signal_direction),
            action_label="View Evidence",
            metrics_json=metrics_json,
            calculations_json=calculations_json,
            display_context={
                "primary_metric": metrics_json[0]["display"] if metrics_json else None,
                "surfaces": ["home", "company_page", "event_page"],
            },
            is_published=publish,
        )
        db.add(card)
        db.flush()

        # Evidence row 1: calculation step (always present when we have a CM).
        if cm and md:
            db.add(
                CardEvidence(
                    card_id=card.card_id,
                    document_id=document.document_id,
                    metric_id=cm.metric_id,
                    evidence_type="calculated_metric",
                    evidence_label=md.metric_name,
                    evidence_value=_metric_display(cm, md),
                    calculation_text=_calculation_text(cm),
                    confidence_score=cm.confidence_score,
                )
            )

        # Evidence rows 2+: every extracted value that fed the metric inputs.
        if cm and isinstance(cm.input_values, dict):
            for input_key in cm.input_values.keys():
                ev = _match_extracted(extracted_by_code, input_key)
                if not ev:
                    continue
                db.add(
                    CardEvidence(
                        card_id=card.card_id,
                        document_id=document.document_id,
                        extracted_value_id=ev.extracted_value_id,
                        evidence_type="source_quote",
                        evidence_label=ev.raw_label,
                        evidence_value=_extracted_evidence_display(ev),
                        source_text=ev.source_text,
                        page_number=ev.page_number,
                        confidence_score=ev.confidence_score,
                    )
                )

        written.append(card)
    return written


# ---------------------------------------------------------------------------
# Result verdict (aggregate hero for QUARTERLY_RESULT events)
# ---------------------------------------------------------------------------


# Card type strings that the frontend treats as "summary" cards — they may
# appear in the feed without a linked `generated_signals` row because they
# aggregate the quarter rather than encode one rule firing.
SUMMARY_CARD_TYPES: frozenset[str] = frozenset({"result_verdict"})


def run_result_verdict(
    db: Session,
    *,
    document: SourceDocument,
    event: CompanyEvent,
    signals: list[GeneratedSignal],
    publish: bool,
) -> IntelligenceCard | None:
    """Emit one ``result_verdict`` card per quarterly result event.

    Mirrors the aggregate header the UI expects: direction is the modal
    direction across fired signals, severity is the most severe, the body
    text reuses the same ``build_event_summary_text`` helper used by the
    legacy stored summary. Returns ``None`` when there is nothing to
    summarise (no fired signals and no event-level direction) so we do not
    publish an empty hero.
    """
    if event.event_type != EventType.QUARTERLY_RESULT:
        return None
    if not signals and not event.overall_signal:
        return None

    from app.services.event_summary import build_event_summary_text

    # Replace any previous verdict for this document so re-runs stay clean.
    existing = list(
        db.scalars(
            select(IntelligenceCard).where(
                IntelligenceCard.document_id == document.document_id,
                IntelligenceCard.card_type == "result_verdict",
            )
        )
    )
    for prev in existing:
        db.execute(delete(CardEvidence).where(CardEvidence.card_id == prev.card_id))
        db.delete(prev)
    if existing:
        db.flush()

    direction, severity = _aggregate_direction_severity(signals, event)
    confidence = _aggregate_confidence(signals)
    headline = _verdict_headline(direction, severity, event)
    summary = build_event_summary_text(signals, []) or headline
    metrics_json = _verdict_metrics_json(db, signals)

    card = IntelligenceCard(
        company_id=document.company_id,
        event_id=document.event_id,
        document_id=document.document_id,
        period_id=document.period_id,
        signal_id=None,
        card_type="result_verdict",
        card_priority=_verdict_priority(severity),
        headline=headline,
        one_line_summary=summary,
        detailed_explanation=summary,
        signal_direction=direction,
        severity=severity,
        confidence_score=confidence,
        confidence_level=_confidence_to_level(confidence),
        investor_question="What is the one-line read on this quarter?",
        watch_next="Track the next event for confirmation or reversal.",
        action_label="Open event detail",
        metrics_json=metrics_json,
        calculations_json={},
        display_context={
            "primary_metric": metrics_json[0]["display"] if metrics_json else None,
            "surfaces": ["home", "company_page", "event_page"],
            "is_summary": True,
        },
        is_published=publish,
    )
    db.add(card)
    db.flush()

    db.add(
        CardEvidence(
            card_id=card.card_id,
            document_id=document.document_id,
            evidence_type="source_document",
            evidence_label=document.document_title,
            evidence_value=event.event_title,
            confidence_score=confidence,
        )
    )

    return card


def _aggregate_direction_severity(
    signals: list[GeneratedSignal],
    event: CompanyEvent,
) -> tuple[SignalDirection, SeverityLevel]:
    if signals:
        counts: dict[SignalDirection, int] = {}
        for s in signals:
            if s.signal_direction is None:
                continue
            counts[s.signal_direction] = counts.get(s.signal_direction, 0) + 1
        if counts:
            direction = max(counts.items(), key=lambda kv: kv[1])[0]
        else:
            direction = event.overall_signal or SignalDirection.NEUTRAL
        severity_rank = {
            SeverityLevel.LOW: 0,
            SeverityLevel.MEDIUM: 1,
            SeverityLevel.HIGH: 2,
            SeverityLevel.CRITICAL: 3,
        }
        ranked = [s for s in signals if s.severity is not None]
        severity = (
            max(ranked, key=lambda s: severity_rank.get(s.severity, 0)).severity
            if ranked
            else event.overall_severity or SeverityLevel.MEDIUM
        )
        return direction, severity
    return event.overall_signal or SignalDirection.NEUTRAL, event.overall_severity or SeverityLevel.MEDIUM


def _aggregate_confidence(signals: list[GeneratedSignal]) -> float:
    scores = [float(s.confidence_score) for s in signals if s.confidence_score is not None]
    if not scores:
        return 70.0
    return round(sum(scores) / len(scores), 2)


def _verdict_priority(severity: SeverityLevel) -> float:
    # Verdicts always rank above their own signal cards so they appear first
    # in the event-page reading flow.
    bump = {
        SeverityLevel.LOW: 40,
        SeverityLevel.MEDIUM: 60,
        SeverityLevel.HIGH: 80,
        SeverityLevel.CRITICAL: 100,
    }
    return float(bump.get(severity, 60)) + 5.0


def _verdict_headline(
    direction: SignalDirection,
    severity: SeverityLevel,
    event: CompanyEvent,
) -> str:
    descriptor = {
        SignalDirection.POSITIVE: "Constructive quarter",
        SignalDirection.NEGATIVE: "Weak quarter",
        SignalDirection.MIXED: "Mixed quarter",
        SignalDirection.NEUTRAL: "In-line quarter",
    }.get(direction, "Quarterly verdict")
    if severity == SeverityLevel.CRITICAL:
        descriptor = "Critical-risk quarter"
    suffix = f" — {event.event_title}" if event.event_title else ""
    return f"{descriptor}{suffix}"


def _verdict_metrics_json(db: Session, signals: list[GeneratedSignal]) -> list[dict]:
    """Top-3 metric snapshot used in the verdict card body."""
    ranked = sorted(signals, key=lambda s: float(s.signal_score or 0), reverse=True)
    out: list[dict] = []
    for sig in ranked:
        if len(out) >= 3:
            break
        if not sig.primary_metric_id:
            continue
        cm = db.get(CalculatedMetric, sig.primary_metric_id)
        if cm is None:
            continue
        md = db.get(MetricDefinition, cm.metric_def_id) if cm.metric_def_id else None
        if not md:
            continue
        out.append(
            {
                "name": md.metric_name,
                "value": float(cm.metric_value) if cm.metric_value is not None else None,
                "unit": cm.unit or md.unit,
                "display": _metric_display(cm, md),
            }
        )
    return out


def _extracted_by_code(db: Session, document_id: int) -> dict[str, ExtractedValue]:
    rows = (
        db.query(ExtractedValue)
        .filter(ExtractedValue.document_id == document_id)
        .all()
    )
    return {ev.normalized_label or ev.raw_label: ev for ev in rows}


def _match_extracted(by_code: dict[str, ExtractedValue], key: str) -> ExtractedValue | None:
    """Best-effort match between a metric input name and an extracted line item.

    Metric input declarations use friendly names like ``revenue`` and
    ``revenue_py``; `_BY_INPUT_NAME` translates those to the normalized codes
    used by extracted values. Suffixes that point at prior periods (``_py``,
    ``_pq``, ``_lyq``) are not in *this* document, so we return None instead
    of accidentally double-citing the current quarter as evidence.
    """
    if not key:
        return None
    aliases = _BY_INPUT_NAME
    code = aliases.get(key)
    if code is None:
        # Unrecognized name — try the raw key (handles new metrics whose input
        # names already match a normalized_code, e.g. `cogs`, `inventory`).
        if any(s in key for s in _PRIOR_PERIOD_SUFFIXES):
            return None
        code = key
    if not code:
        return None
    return by_code.get(code)


_PRIOR_PERIOD_SUFFIXES: tuple[str, ...] = ("_py", "_pq", "_lyq", "_ttm")


_BY_INPUT_NAME: dict[str, str | None] = {
    # P&L
    "revenue": "revenue_from_operations",
    "revenue_cq": "revenue_from_operations",
    "ebitda": "ebitda",
    "ebitda_cq": "ebitda",
    "pbt": "pbt",
    "pat": "pat",
    "other_income": "other_income",
    "exceptional_items": "exceptional_items",
    "tax": "tax_expense",
    "finance_cost": "finance_cost",
    "depreciation": "depreciation",
    "cogs": "cogs",
    # Cash flow / WC
    "cfo": "cfo",
    "capex_ppe": "capex_ppe",
    "capex_intangibles": "capex_intangibles",
    "rec": "trade_receivables",
    "inv": "inventory",
    "pay": "trade_payables",
    "avg_rec": "trade_receivables",
    "avg_inv": "inventory",
    "avg_pay": "trade_payables",
    # Balance sheet
    "short": "short_term_borrowings",
    "long": "long_term_borrowings",
    "lease": "lease_liabilities",
    "cash": "cash_and_equivalents",
    "equity": "shareholders_equity",
    # Market
    "price": "share_price_close",
    "vol": "volume",
    "avg_vol": "avg_volume_20d",
    "mcap": "market_cap",
    "pre": "pre_event_close",
    "post": "post_event_close",
    # Guidance / order book
    "lo": None,
    "hi": None,
    "now": None,
    "ob": "closing_order_book",
    "inflow": "order_inflow",
    "cancelled": "cancelled_orders",
    "top": "top_customer_orders",
    "dps": "dividend_per_share",
    "order_val": "new_order_value",
    "deal": "acquisition_value",
    "new_cap": "new_capacity",
    "exist_cap": "existing_capacity",
    "tam": "tam_market_size",
    "tam_py": "tam_market_size_prior",
    "rev": "primary_segment_revenue",
    "ebit_seg": "primary_segment_ebit",
}


def _card_priority(sig: GeneratedSignal) -> float:
    """Mirror the seed's priority scaling so feed ordering stays consistent."""
    sev_weight = {
        SeverityLevel.LOW: 35,
        SeverityLevel.MEDIUM: 55,
        SeverityLevel.HIGH: 75,
        SeverityLevel.CRITICAL: 95,
    }
    return float(sev_weight.get(sig.severity, 55))


def _confidence_to_level(score: float) -> ConfidenceLevel:
    if score >= 85:
        return ConfidenceLevel.HIGH
    if score >= 65:
        return ConfidenceLevel.MEDIUM
    if score >= 40:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.NEEDS_REVIEW


def _metrics_json_for(
    cm: CalculatedMetric | None, md: MetricDefinition | None
) -> list[dict]:
    if not cm or not md:
        return []
    return [
        {
            "name": md.metric_name,
            "value": float(cm.metric_value) if cm.metric_value is not None else None,
            "unit": cm.unit or md.unit,
            "display": _metric_display(cm, md),
        }
    ]


def _extracted_evidence_display(ev: ExtractedValue) -> str | None:
    """Prefer document-style numbers over Python float stringification."""
    if ev.numeric_value is None:
        return ev.raw_value
    val = float(ev.numeric_value)
    unit = (ev.unit or "").strip().lower()
    if unit == "%":
        return f"{val:.1f}%"
    if unit == "bps":
        return f"{val:+.0f} bps"
    if unit in ("rs", "inr"):
        if abs(val - round(val)) < 1e-6:
            return f"Rs {int(round(val)):,}"
        return f"Rs {val:,.2f}".rstrip("0").rstrip(".")
    if abs(val - round(val)) < 1e-6:
        return f"{int(round(val)):,}"
    text = f"{val:.4f}".rstrip("0").rstrip(".")
    whole, _, frac = text.partition(".")
    return f"{int(whole):,}.{frac}" if frac else f"{int(whole):,}"


def _metric_display(cm: CalculatedMetric, md: MetricDefinition) -> str:
    if cm.metric_value is None:
        return "—"
    val = float(cm.metric_value)
    unit = cm.unit or md.unit or ""
    if unit == "%":
        return f"{val:.1f}%"
    if unit == "bps":
        return f"{val:+.0f} bps"
    if unit == "x":
        return f"{val:.2f}x"
    return f"{val:.2f}"


def _calculations_json_for(cm: CalculatedMetric | None) -> dict:
    if not cm:
        return {}
    steps = cm.calculation_steps or {}
    return {
        "formula": steps.get("formula"),
        "calculation_steps": steps.get("steps", []),
        "inputs": steps.get("inputs", {}),
    }


def _calculation_text(cm: CalculatedMetric) -> str | None:
    steps = (cm.calculation_steps or {}).get("steps")
    if not steps:
        return None
    return " · ".join(str(s) for s in steps)


def _one_liner(
    sig: GeneratedSignal, cm: CalculatedMetric | None, md: MetricDefinition | None
) -> str:
    """Short summary surfaced in the feed/drawer."""
    if cm and md:
        return (
            f"{md.metric_name} at {_metric_display(cm, md)} for this period — "
            f"triggers {sig.headline or 'signal'}."
        )
    return sig.headline or "Signal triggered by ingestion pipeline."


def _investor_question(sd: SignalDefinition, direction: SignalDirection) -> str:
    """Default investor question for this signal category."""
    return {
        "margin": "Is the margin shift structural or one-off?",
        "growth": "Is the growth rate sustainable into the next quarter?",
        "profit_quality": "How much of reported PAT is operating earnings vs other income?",
        "expense": "Are these costs run-rate or capex-led?",
        "debt": "Is leverage rising and how does it affect interest coverage?",
        "red_flag": "Does management have a credible answer for this flag?",
        "cashflow": "Is operating cashflow keeping pace with PAT?",
    }.get(sd.signal_category, "What changed this quarter that the market may have missed?")


def _watch_next(sd: SignalDefinition, direction: SignalDirection) -> str:
    return {
        "margin": "Track gross margin and operating leverage in the next quarter.",
        "growth": "Watch order book / new deal wins for sustained growth.",
        "profit_quality": "Monitor the share of other income in PBT next quarter.",
        "expense": "Compare finance cost trajectory against EBITDA growth.",
        "debt": "Track total debt and interest coverage ratios quarter-on-quarter.",
        "red_flag": "Follow auditor commentary in the next filing.",
        "cashflow": "Reconcile CFO with PAT once the cashflow statement lands.",
    }.get(sd.signal_category, "Track this metric next quarter.")
