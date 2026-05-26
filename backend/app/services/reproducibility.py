"""Assemble the analyst-reproducibility bundle for a single card.

This is the Phase 3 deliverable from the metric-governance roadmap. The
bundle answers the question "how did this card come to exist?" with one
self-contained JSON payload — signal rule, metric formula, resolved inputs,
source quotes, pipeline versions, and a navigable lineage graph from
extracted value all the way up to the card.

The shape is consumed by:
- ``GET /v1/intelligence-objects/{id}/reproducibility`` (download bundle)
- ``IntelligenceObjectPage`` ExtractionLineageGraph (renders the graph)

All logic here is read-only.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.events import ExtractionJob
from app.models.facts import ExtractedValue, FinancialStatementFact
from app.models.intelligence import (
    CalculatedMetric,
    CardEvidence,
    GeneratedSignal,
    IntelligenceCard,
    MetricDefinition,
    SignalDefinition,
)
from app.schemas.v1.reproducibility import (
    LineageEdge,
    LineageGraph,
    LineageNode,
    ReproducibilityAuditTrail,
    ReproducibilityBundle,
    ReproducibilityCard,
    ReproducibilityInput,
    ReproducibilityMetric,
    ReproducibilitySignal,
)


def build_reproducibility_bundle(
    db: Session, card: IntelligenceCard
) -> ReproducibilityBundle:
    """Return the full bundle for ``card``.

    Result cards (``result_verdict``) have no underlying signal — the
    bundle is still produced but with ``signal=None`` and ``metric=None``,
    surfacing only the audit trail and the card-level lineage edge.
    """
    signal_row, signal_def = _load_signal(db, card)
    cm, md = _load_metric(db, signal_row)

    inputs = _build_inputs(db, cm, md, card.document_id)
    metric = _build_metric(cm, md, inputs)
    signal = _build_signal(signal_row, signal_def)
    audit = _build_audit_trail(db, card)
    lineage = _build_lineage(db, card, signal_row, cm, inputs)

    return ReproducibilityBundle(
        card=ReproducibilityCard(
            card_id=card.card_id,
            card_type=card.card_type,
            headline=card.headline,
            one_line_summary=card.one_line_summary,
            direction=card.signal_direction.value if card.signal_direction else None,
            severity=card.severity.value if card.severity else None,
            confidence_score=(
                float(card.confidence_score) if card.confidence_score is not None else None
            ),
            is_published=bool(card.is_published),
        ),
        signal=signal,
        metric=metric,
        audit_trail=audit,
        lineage=lineage,
        exported_at=datetime.now(timezone.utc),
    )


def _load_signal(
    db: Session, card: IntelligenceCard
) -> tuple[GeneratedSignal | None, SignalDefinition | None]:
    if card.signal_id is None:
        return None, None
    sig = db.get(GeneratedSignal, card.signal_id)
    if sig is None:
        return None, None
    sd = db.get(SignalDefinition, sig.signal_def_id)
    return sig, sd


def _load_metric(
    db: Session, signal_row: GeneratedSignal | None
) -> tuple[CalculatedMetric | None, MetricDefinition | None]:
    if signal_row is None or signal_row.primary_metric_id is None:
        return None, None
    cm = db.get(CalculatedMetric, signal_row.primary_metric_id)
    if cm is None:
        return None, None
    md = db.get(MetricDefinition, cm.metric_def_id) if cm.metric_def_id else None
    return cm, md


def _build_inputs(
    db: Session,
    cm: CalculatedMetric | None,
    md: MetricDefinition | None,
    document_id: int | None,
) -> list[ReproducibilityInput]:
    if cm is None:
        return []
    runtime: dict = dict(cm.input_values or {})
    decls = list((md.inputs_json or []) if md else [])
    decl_by_name = {
        d.get("name"): d for d in decls if isinstance(d, dict) and d.get("name")
    }
    extracted_by_code = _extracted_lookup(db, document_id) if document_id else {}

    out: list[ReproducibilityInput] = []
    for name, value in runtime.items():
        decl = decl_by_name.get(name) or {}
        code = decl.get("code")
        scope = (decl.get("scope") or "CURRENT").upper()
        kind = (decl.get("kind") or "fact").lower()
        ev: ExtractedValue | None = None
        if kind == "fact" and scope == "CURRENT" and code:
            ev = extracted_by_code.get(code)
        try:
            numeric: float | None = float(value) if value is not None else None
        except (TypeError, ValueError):
            numeric = None
        out.append(
            ReproducibilityInput(
                name=name,
                code=code,
                scope=scope,
                kind=kind,
                value=numeric,
                unit=ev.unit if ev else None,
                extracted_value_id=ev.extracted_value_id if ev else None,
                page_number=ev.page_number if ev else None,
                source_text=ev.source_text if ev else None,
                confidence_score=(
                    float(ev.confidence_score)
                    if ev is not None and ev.confidence_score is not None
                    else None
                ),
            )
        )
    return out


def _build_metric(
    cm: CalculatedMetric | None,
    md: MetricDefinition | None,
    inputs: list[ReproducibilityInput],
) -> ReproducibilityMetric | None:
    if cm is None:
        return None
    return ReproducibilityMetric(
        metric_id=cm.metric_id,
        code=md.metric_code if md else None,
        name=md.metric_name if md else None,
        metric_kind=md.metric_kind if md else None,
        formula_text=md.formula_text if md else None,
        unit=cm.unit or (md.unit if md else None),
        value=float(cm.metric_value) if cm.metric_value is not None else None,
        validation_min=(
            float(md.validation_min) if md and md.validation_min is not None else None
        ),
        validation_max=(
            float(md.validation_max) if md and md.validation_max is not None else None
        ),
        is_quarantined=bool(getattr(cm, "is_quarantined", False)),
        quarantine_reason=getattr(cm, "quarantine_reason", None),
        anomaly_flag=bool(getattr(cm, "anomaly_flag", False)),
        anomaly_reason=getattr(cm, "anomaly_reason", None),
        confidence_score=(
            float(cm.confidence_score) if cm.confidence_score is not None else None
        ),
        inputs=inputs,
    )


def _build_signal(
    signal_row: GeneratedSignal | None,
    signal_def: SignalDefinition | None,
) -> ReproducibilitySignal | None:
    if signal_row is None and signal_def is None:
        return None
    fired_value: float | None = None
    threshold: float | None = None
    operator: str | None = None
    refs = list(signal_row.metric_refs or []) if signal_row else []
    if refs and isinstance(refs[0], dict):
        head = refs[0]
        fired_value = float(head["value"]) if head.get("value") is not None else None
        threshold = (
            float(head["threshold"]) if head.get("threshold") is not None else None
        )
        operator = head.get("op")
    return ReproducibilitySignal(
        signal_id=signal_row.signal_id if signal_row else None,
        code=signal_def.signal_code if signal_def else None,
        name=signal_def.signal_name if signal_def else None,
        category=signal_def.signal_category if signal_def else None,
        rule_text=signal_def.rule_text if signal_def else None,
        direction=(
            signal_row.signal_direction.value
            if signal_row and signal_row.signal_direction
            else None
        ),
        severity=(
            signal_row.severity.value if signal_row and signal_row.severity else None
        ),
        confidence_score=(
            float(signal_row.confidence_score)
            if signal_row and signal_row.confidence_score is not None
            else None
        ),
        fired_value=fired_value,
        threshold=threshold,
        operator=operator,
        explanation=signal_row.explanation if signal_row else None,
    )


def _build_audit_trail(
    db: Session, card: IntelligenceCard
) -> ReproducibilityAuditTrail | None:
    """Hydrate the audit trail.

    Cards written after Phase 3 carry an ``audit_trail`` snapshot in
    ``display_context``; older cards fall back to the active
    ``ExtractionJob`` row for the same document.
    """
    snapshot = (card.display_context or {}).get("audit_trail") if card.display_context else None
    if isinstance(snapshot, dict) and snapshot:
        return ReproducibilityAuditTrail(
            extraction_job_id=snapshot.get("extraction_job_id"),
            prompt_version=snapshot.get("prompt_version"),
            parser_version=snapshot.get("parser_version"),
            model_name=snapshot.get("model_name"),
            provider_used=snapshot.get("provider_used"),
            llm_temperature=snapshot.get("llm_temperature"),
            llm_seed=snapshot.get("llm_seed"),
            request_hash=snapshot.get("request_hash"),
            completed_at=_parse_dt(snapshot.get("completed_at")),
            reprocess_timestamp=_parse_dt(snapshot.get("reprocess_timestamp")),
        )
    if card.document_id is None:
        return None
    job = db.scalar(
        select(ExtractionJob)
        .where(ExtractionJob.document_id == card.document_id)
        .order_by(ExtractionJob.created_at.desc())
        .limit(1)
    )
    if job is None:
        return None
    return ReproducibilityAuditTrail(
        extraction_job_id=job.extraction_job_id,
        prompt_version=job.prompt_version,
        parser_version=job.parser_version,
        model_name=job.model_name,
        provider_used=job.provider_used,
        llm_temperature=(
            float(job.llm_temperature) if job.llm_temperature is not None else None
        ),
        llm_seed=job.llm_seed,
        request_hash=job.request_hash,
        completed_at=job.completed_at,
    )


def _build_lineage(
    db: Session,
    card: IntelligenceCard,
    signal_row: GeneratedSignal | None,
    cm: CalculatedMetric | None,
    inputs: list[ReproducibilityInput],
) -> LineageGraph:
    """Build the ``ExtractedValue → Fact → Metric → Signal → Card`` graph."""
    nodes: list[LineageNode] = []
    edges: list[LineageEdge] = []
    seen_ids: set[str] = set()

    def add_node(node: LineageNode) -> None:
        if node.id in seen_ids:
            return
        seen_ids.add(node.id)
        nodes.append(node)

    card_id = f"intelligence_card:{card.card_id}"
    add_node(
        LineageNode(
            id=card_id,
            kind="intelligence_card",
            label=card.headline,
            detail=card.card_type,
            document_id=card.document_id,
            confidence_score=(
                float(card.confidence_score) if card.confidence_score is not None else None
            ),
        )
    )

    signal_id_str: str | None = None
    if signal_row is not None:
        signal_id_str = f"generated_signal:{signal_row.signal_id}"
        add_node(
            LineageNode(
                id=signal_id_str,
                kind="generated_signal",
                label=(
                    signal_row.headline
                    or (
                        signal_row.signal_direction.value
                        if signal_row.signal_direction
                        else "signal"
                    )
                ),
                detail=signal_row.explanation,
                confidence_score=(
                    float(signal_row.confidence_score)
                    if signal_row.confidence_score is not None
                    else None
                ),
            )
        )
        edges.append(
            LineageEdge(source=signal_id_str, target=card_id, relationship="signal_to_card")
        )

    metric_id_str: str | None = None
    if cm is not None:
        metric_id_str = f"calculated_metric:{cm.metric_id}"
        if getattr(cm, "is_quarantined", False):
            status = "quarantined"
        elif getattr(cm, "anomaly_flag", False):
            status = "anomaly"
        else:
            status = "validated"
        add_node(
            LineageNode(
                id=metric_id_str,
                kind="calculated_metric",
                label=str(cm.metric_value) if cm.metric_value is not None else "metric",
                detail=cm.unit,
                confidence_score=(
                    float(cm.confidence_score)
                    if cm.confidence_score is not None
                    else None
                ),
                validation_status=status,
            )
        )
        if signal_id_str is not None:
            edges.append(
                LineageEdge(
                    source=metric_id_str,
                    target=signal_id_str,
                    relationship="metric_to_signal",
                )
            )
        else:
            edges.append(
                LineageEdge(
                    source=metric_id_str,
                    target=card_id,
                    relationship="metric_to_card",
                )
            )

    # Anchor each metric input back to its ExtractedValue + linked Fact.
    fact_rows = (
        _fact_for_extracted_values(db, [i.extracted_value_id for i in inputs])
        if cm is not None
        else {}
    )
    for inp in inputs:
        if inp.extracted_value_id is None:
            continue
        ev_node_id = f"extracted_value:{inp.extracted_value_id}"
        add_node(
            LineageNode(
                id=ev_node_id,
                kind="extracted_value",
                label=inp.name,
                detail=(
                    f"{inp.value} {inp.unit or ''}".strip()
                    if inp.value is not None
                    else inp.source_text
                ),
                page_number=inp.page_number,
                confidence_score=inp.confidence_score,
            )
        )
        fact = fact_rows.get(inp.extracted_value_id)
        if fact is not None:
            fact_node_id = f"financial_fact:{fact.fact_id}"
            add_node(
                LineageNode(
                    id=fact_node_id,
                    kind="financial_fact",
                    label=str(fact.value),
                    detail=fact.unit,
                    confidence_score=(
                        float(fact.confidence_score)
                        if fact.confidence_score is not None
                        else None
                    ),
                )
            )
            edges.append(
                LineageEdge(
                    source=ev_node_id,
                    target=fact_node_id,
                    relationship="extracted_to_fact",
                )
            )
            if metric_id_str is not None:
                edges.append(
                    LineageEdge(
                        source=fact_node_id,
                        target=metric_id_str,
                        relationship="fact_to_metric",
                    )
                )
        elif metric_id_str is not None:
            edges.append(
                LineageEdge(
                    source=ev_node_id,
                    target=metric_id_str,
                    relationship="extracted_to_metric",
                )
            )

    # Add any card-evidence source quotes that were not already linked
    # through the metric inputs — keeps the graph honest for cards whose
    # evidence rows reference values outside the primary metric (e.g. the
    # supporting management commentary on a margin card).
    extra_evidence = db.scalars(
        select(CardEvidence).where(
            CardEvidence.card_id == card.card_id,
            CardEvidence.extracted_value_id.is_not(None),
        )
    ).all()
    seen_ev_ids = {i.extracted_value_id for i in inputs if i.extracted_value_id is not None}
    for ev in extra_evidence:
        if ev.extracted_value_id in seen_ev_ids:
            continue
        ev_node_id = f"extracted_value:{ev.extracted_value_id}"
        add_node(
            LineageNode(
                id=ev_node_id,
                kind="extracted_value",
                label=ev.evidence_label or "evidence",
                detail=ev.evidence_value,
                page_number=ev.page_number,
                confidence_score=(
                    float(ev.confidence_score)
                    if ev.confidence_score is not None
                    else None
                ),
            )
        )
        edges.append(
            LineageEdge(
                source=ev_node_id,
                target=card_id,
                relationship="evidence_to_card",
            )
        )

    return LineageGraph(nodes=nodes, edges=edges)


def _extracted_lookup(db: Session, document_id: int) -> dict[str, ExtractedValue]:
    rows = db.scalars(
        select(ExtractedValue).where(ExtractedValue.document_id == document_id)
    ).all()
    out: dict[str, ExtractedValue] = {}
    for ev in rows:
        code = ev.normalized_label
        if code and code not in out:
            out[code] = ev
    return out


def _fact_for_extracted_values(
    db: Session, extracted_value_ids: list[int | None]
) -> dict[int, FinancialStatementFact]:
    ids = [i for i in extracted_value_ids if i is not None]
    if not ids:
        return {}
    rows = db.scalars(
        select(FinancialStatementFact).where(
            FinancialStatementFact.source_extracted_value_id.in_(ids)
        )
    ).all()
    out: dict[int, FinancialStatementFact] = {}
    for fact in rows:
        if fact.source_extracted_value_id is not None:
            out[fact.source_extracted_value_id] = fact
    return out


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None
