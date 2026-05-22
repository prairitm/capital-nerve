"""Context loaders for signal detail page."""

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.events import CompanyEvent, SourceDocument
from app.models.intelligence import CardEvidence, GeneratedSignal, IntelligenceCard, SignalDefinition
from app.models.master import Company, FinancialPeriod, Sector
from app.routers._helpers import card_brief
from app.schemas.common import DocumentBrief, EvidenceItem
from app.services.card_context import load_metric_comparisons, load_trend_sparklines


def _op_label(op: str) -> str:
    return {">": "above", ">=": "at or above", "<": "below", "<=": "at or below"}.get(op, op)


def _format_rule(rule: dict) -> str | None:
    if not rule:
        return None
    metric = rule.get("metric", "").replace("_", " ")
    op = rule.get("operator", "")
    threshold = rule.get("threshold")
    if not metric or not op:
        return None
    op_label = _op_label(op)
    if threshold is not None:
        return f"Fires when {metric} is {op_label} {threshold}"
    return f"Fires when {metric} is {op_label} threshold"


def _collect_rule_metric_codes(rule: dict) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()

    def walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        if "metric" in node:
            code = str(node["metric"])
            if code not in seen:
                seen.add(code)
                codes.append(code)
            return
        for key in ("all", "any"):
            if key in node:
                for child in node[key]:
                    walk(child)
        if "not" in node:
            walk(node["not"])

    walk(rule)
    return codes


def _format_rule_tree(rule: dict) -> str | None:
    simple = _format_rule(rule)
    if simple:
        return simple

    def fmt(node: object) -> str:
        if not isinstance(node, dict):
            return ""
        if "metric" in node:
            metric = str(node["metric"]).replace("_", " ")
            op = str(node.get("operator", ""))
            threshold = node.get("threshold")
            op_label = _op_label(op)
            if threshold is not None:
                return f"{metric} is {op_label} {threshold}"
            return f"{metric} is {op_label} threshold"
        if "all" in node:
            parts = [fmt(child) for child in node["all"]]
            parts = [p for p in parts if p]
            return " and ".join(parts)
        if "any" in node:
            parts = [fmt(child) for child in node["any"]]
            parts = [p for p in parts if p]
            if len(parts) > 1:
                return f"({' or '.join(parts)})"
            return parts[0] if parts else ""
        return ""

    body = fmt(rule)
    return f"Fires when {body}" if body else None


def _find_leaf_in_rule(rule: dict, code: str) -> dict | None:
    if rule.get("metric") == code:
        return rule
    for key in ("all", "any"):
        if key in rule:
            for child in rule[key]:
                if isinstance(child, dict):
                    found = _find_leaf_in_rule(child, code)
                    if found:
                        return found
    if "not" in rule and isinstance(rule["not"], dict):
        return _find_leaf_in_rule(rule["not"], code)
    return None


def _compare_metric(value: float, op: str, threshold: float) -> bool:
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    if op == "==":
        return value == threshold
    if op == "!=":
        return value != threshold
    return False


def _build_rule_leaves(
    metric_refs: list[Any],
    comparisons: list[dict[str, Any]],
    rule: dict,
) -> list[dict[str, Any]]:
    by_code = {row["metric_code"]: row for row in comparisons}
    ref_by_code: dict[str, dict[str, Any]] = {}
    for ref in metric_refs:
        if isinstance(ref, dict) and ref.get("metric_code"):
            ref_by_code[str(ref["metric_code"])] = ref

    codes: list[str] = []
    for ref in metric_refs:
        if isinstance(ref, dict) and (code := ref.get("metric_code")) and code not in codes:
            codes.append(str(code))
    for code in _collect_rule_metric_codes(rule):
        if code not in codes:
            codes.append(code)

    leaves: list[dict[str, Any]] = []
    for code in codes:
        comp = by_code.get(code)
        ref = ref_by_code.get(code)
        leaf_rule = _find_leaf_in_rule(rule, code) if rule else None

        op = (ref or {}).get("op") or (leaf_rule or {}).get("operator")
        threshold = (ref or {}).get("threshold")
        if threshold is None and leaf_rule:
            threshold = leaf_rule.get("threshold")

        value: float | None = None
        unit = ""
        if ref and ref.get("value") is not None:
            value = float(ref["value"])
            unit = str(ref.get("unit") or "")
        elif comp and comp.get("current_value") is not None:
            value = float(comp["current_value"])
            unit = str(comp.get("unit") or "")

        passed: bool | None = None
        if value is not None and op and threshold is not None:
            passed = _compare_metric(value, str(op), float(threshold))

        rule_text: str | None = None
        if op and threshold is not None:
            rule_text = f"Requires {_op_label(str(op))} {threshold}"

        leaves.append(
            {
                "metric_code": code,
                "metric_name": comp["metric_name"] if comp else code.replace("_", " ").title(),
                "current_value": value,
                "unit": unit,
                "operator": op,
                "threshold": threshold,
                "passed": passed,
                "rule_text": rule_text,
            }
        )
    return leaves


def _sort_metric_comparisons(
    comparisons: list[dict[str, Any]],
    rule_codes: list[str],
) -> list[dict[str, Any]]:
    if not rule_codes:
        return comparisons
    priority = {code: idx for idx, code in enumerate(rule_codes)}
    return sorted(comparisons, key=lambda row: priority.get(row.get("metric_code", ""), 999))


def _load_related_cards(
    db: Session,
    sig: GeneratedSignal,
    company: Company,
) -> list[dict[str, Any]]:
    stmt = (
        select(IntelligenceCard, Company, FinancialPeriod, CompanyEvent, SourceDocument)
        .join(Company, Company.company_id == IntelligenceCard.company_id)
        .outerjoin(FinancialPeriod, FinancialPeriod.period_id == IntelligenceCard.period_id)
        .outerjoin(CompanyEvent, CompanyEvent.event_id == IntelligenceCard.event_id)
        .outerjoin(SourceDocument, SourceDocument.document_id == IntelligenceCard.document_id)
        .where(IntelligenceCard.company_id == company.company_id)
        .where(IntelligenceCard.card_type != "watch_next")
    )
    if sig.event_id:
        stmt = stmt.where(
            or_(
                IntelligenceCard.signal_id == sig.signal_id,
                IntelligenceCard.event_id == sig.event_id,
            )
        )
    else:
        stmt = stmt.where(IntelligenceCard.signal_id == sig.signal_id)

    rows = db.execute(
        stmt.order_by(IntelligenceCard.card_priority.desc(), IntelligenceCard.created_at.desc()).limit(12)
    ).all()

    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for card, comp, per, ev, doc in rows:
        if card.card_id in seen:
            continue
        seen.add(card.card_id)
        out.append(card_brief(card, comp, per, ev, doc).model_dump(mode="json"))
    return out


def _load_evidence(db: Session, sig: GeneratedSignal) -> list[EvidenceItem]:
    card_ids = db.scalars(
        select(IntelligenceCard.card_id).where(IntelligenceCard.signal_id == sig.signal_id)
    ).all()
    if not card_ids and sig.event_id:
        card_ids = db.scalars(
            select(IntelligenceCard.card_id).where(
                IntelligenceCard.event_id == sig.event_id,
                IntelligenceCard.card_type != "watch_next",
            )
        ).all()
    if not card_ids:
        return []

    rows = db.scalars(
        select(CardEvidence)
        .where(CardEvidence.card_id.in_(card_ids))
        .order_by(CardEvidence.card_evidence_id)
        .limit(12)
    ).all()
    return [
        EvidenceItem(
            card_evidence_id=e.card_evidence_id,
            document_id=e.document_id,
            evidence_type=e.evidence_type,
            evidence_label=e.evidence_label,
            evidence_value=e.evidence_value,
            source_text=e.source_text,
            page_number=e.page_number,
            calculation_text=e.calculation_text,
            confidence_score=float(e.confidence_score) if e.confidence_score is not None else None,
        )
        for e in rows
    ]


def _signal_query():
    return (
        select(GeneratedSignal, SignalDefinition, Company, Sector, FinancialPeriod)
        .join(SignalDefinition, SignalDefinition.signal_def_id == GeneratedSignal.signal_def_id)
        .join(Company, Company.company_id == GeneratedSignal.company_id)
        .join(Sector, Sector.sector_id == Company.sector_id, isouter=True)
        .outerjoin(FinancialPeriod, FinancialPeriod.period_id == GeneratedSignal.period_id)
        .where(GeneratedSignal.is_published.is_(True))
    )


def _signal_brief(sig: GeneratedSignal, sd: SignalDefinition) -> dict[str, Any]:
    return {
        "signal_id": sig.signal_id,
        "signal_code": sd.signal_code,
        "signal_name": sd.signal_name,
        "signal_category": sd.signal_category,
        "direction": sig.signal_direction.value,
        "severity": sig.severity.value,
        "confidence_score": float(sig.confidence_score) if sig.confidence_score is not None else None,
        "signal_score": float(sig.signal_score) if sig.signal_score is not None else None,
        "headline": sig.headline,
    }


def _load_related_signals(db: Session, sig: GeneratedSignal) -> list[dict[str, Any]]:
    stmt = (
        _signal_query()
        .where(GeneratedSignal.company_id == sig.company_id)
        .where(GeneratedSignal.signal_id != sig.signal_id)
    )
    if sig.period_id:
        stmt = stmt.where(
            or_(GeneratedSignal.period_id == sig.period_id, GeneratedSignal.period_id.is_(None))
        )
    rows = db.execute(
        stmt.order_by(GeneratedSignal.signal_score.desc().nullslast()).limit(6)
    ).all()
    return [_signal_brief(s, d) for s, d, *_ in rows]


def enrich_signal_detail(
    db: Session,
    sig: GeneratedSignal,
    sd: SignalDefinition,
    comp: Company,
    sec: Sector | None,
    per: FinancialPeriod | None,
    base: dict[str, Any],
) -> dict[str, Any]:
    rule = sd.rule_json or {}
    metric_refs = sig.metric_refs or []
    base["rule_json"] = rule
    base["rule_summary"] = _format_rule_tree(rule) or sd.rule_text
    base["rule_metric_codes"] = _collect_rule_metric_codes(rule)

    period_id = per.period_id if per else None
    comparisons = [
        m.model_dump(mode="json")
        for m in load_metric_comparisons(db, comp.company_id, period_id, sig.event_id, sd.signal_category)
    ]
    base["metric_comparisons"] = _sort_metric_comparisons(comparisons, base["rule_metric_codes"])
    base["rule_leaves"] = _build_rule_leaves(metric_refs, base["metric_comparisons"], rule)
    base["trend_sparklines"] = [
        t.model_dump(mode="json") for t in load_trend_sparklines(db, comp.company_id, period_id)
    ]
    base["related_cards"] = _load_related_cards(db, sig, comp)
    base["evidence"] = [e.model_dump(mode="json") for e in _load_evidence(db, sig)]
    base["related_signals"] = _load_related_signals(db, sig)

    trigger_code: str | None = None
    if metric_refs and isinstance(metric_refs[0], dict):
        trigger_code = metric_refs[0].get("metric_code")
    if not trigger_code:
        trigger_code = rule.get("metric")
    if not trigger_code and base["rule_metric_codes"]:
        trigger_code = base["rule_metric_codes"][0]

    if trigger_code:
        for row in base["metric_comparisons"]:
            if row.get("metric_code") == trigger_code:
                base["trigger_metric"] = row
                break

    if metric_refs and isinstance(metric_refs[0], dict):
        ref = metric_refs[0]
        code = ref.get("metric_code")
        comp = next(
            (row for row in base["metric_comparisons"] if row.get("metric_code") == code),
            None,
        )
        base["primary_metric"] = {
            "metric_code": code,
            "metric_name": comp["metric_name"] if comp else str(code).replace("_", " ").title(),
            "value": ref.get("value"),
            "unit": ref.get("unit") or (comp.get("unit") if comp else ""),
        }
    else:
        base["primary_metric"] = None

    if sig.event_id:
        event = db.get(CompanyEvent, sig.event_id)
        if event:
            base["event"] = {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "event_title": event.event_title,
                "event_date": event.event_date.isoformat(),
                "summary_text": event.summary_text,
                "main_issue": event.main_issue,
                "watch_next": event.watch_next,
                "overall_signal": event.overall_signal.value if event.overall_signal else None,
                "overall_severity": event.overall_severity.value if event.overall_severity else None,
                "overall_confidence": float(event.overall_confidence)
                if event.overall_confidence is not None
                else None,
            }

    if sig.document_id:
        doc = db.get(SourceDocument, sig.document_id)
        if doc:
            base["document"] = DocumentBrief(
                document_id=doc.document_id,
                document_type=doc.document_type,
                document_title=doc.document_title,
                document_date=doc.document_date,
                extraction_confidence=float(doc.extraction_confidence)
                if doc.extraction_confidence is not None
                else None,
                values_extracted=doc.values_extracted,
                cards_generated=doc.cards_generated,
            ).model_dump(mode="json")

    return base
