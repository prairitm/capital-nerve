#!/usr/bin/env python3
"""Export current SQLite extraction outputs in accuracy-evaluator JSONL format."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from .evaluate import EvaluationInputError, load_jsonl
except ImportError:  # Direct execution: python accuracy/baseline_from_db.py
    from evaluate import EvaluationInputError, load_jsonl


def make_label_id(
    document_id: str,
    fact_code: str,
    period_end: str,
    basis: str,
    period_type: str,
) -> str:
    return ":".join(
        [document_id[:8], fact_code, period_end, basis, period_type]
    )


def export_predictions(
    database: str | Path, gold_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    document_ids = {record["document_id"] for record in gold_records}
    fact_codes = {record["fact_code"] for record in gold_records}
    if not document_ids or not fact_codes:
        return []

    connection = sqlite3.connect(
        f"file:{Path(database).resolve()}?mode=ro", uri=True
    )
    connection.row_factory = sqlite3.Row
    document_placeholders = ",".join("?" for _ in document_ids)
    fact_placeholders = ",".join("?" for _ in fact_codes)
    query = f"""
        SELECT c.ticker AS company_symbol,
               e.document_id,
               ev.value_code AS fact_code,
               ev.value_numeric,
               ev.value_text,
               ev.unit,
               ev.period_end,
               ev.period_type,
               ev.basis,
               ev.segment,
               ev.geography,
               ev.source_page,
               ev.source_text,
               ev.confidence
        FROM extracted_values ev
        JOIN events e ON e.id = ev.event_id
        JOIN companies c ON c.id = ev.company_id
        WHERE e.document_id IN ({document_placeholders})
          AND ev.value_code IN ({fact_placeholders})
    """
    params = [*sorted(document_ids), *sorted(fact_codes)]
    rows = [dict(row) for row in connection.execute(query, params)]
    connection.close()

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        required_identity = (
            row.get("document_id"),
            row.get("fact_code"),
            row.get("period_end"),
            row.get("basis"),
            row.get("period_type"),
        )
        if not all(isinstance(value, str) and value for value in required_identity):
            continue
        label_id = make_label_id(*required_identity)
        grouped[label_id].append(row)

    predictions: list[dict[str, Any]] = []
    for label_id, candidates in sorted(grouped.items()):
        selected = max(
            candidates,
            key=lambda row: (
                float(row.get("confidence") or 0.0),
                str(row.get("value_numeric")),
                str(row.get("value_text")),
            ),
        )
        distinct_values = {
            (row.get("value_numeric"), row.get("value_text"), row.get("unit"))
            for row in candidates
        }
        predictions.append(
            {
                "label_id": label_id,
                "decision": "publish",
                "document_id": selected["document_id"],
                "company_symbol": selected["company_symbol"],
                "fact_code": selected["fact_code"],
                "value_numeric": selected.get("value_numeric"),
                "value_text": selected.get("value_text"),
                "unit": selected.get("unit"),
                "period_end": selected["period_end"],
                "period_type": selected["period_type"],
                "basis": selected["basis"],
                "source_page": selected.get("source_page"),
                "source_text": selected.get("source_text"),
                "segment": selected.get("segment"),
                "geography": selected.get("geography"),
                "confidence": selected.get("confidence"),
                "extraction_method": "existing_extracted_values",
                "has_unresolved_conflict": len(distinct_values) > 1,
                "candidate_count": len(candidates),
            }
        )
    return predictions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        gold_records = load_jsonl(args.gold)
    except EvaluationInputError as exc:
        parser.error(str(exc))
    predictions = export_predictions(args.database, gold_records)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in predictions),
        encoding="utf-8",
    )
    print(f"Exported {len(predictions)} predictions to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
