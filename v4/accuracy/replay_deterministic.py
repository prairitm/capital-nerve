#!/usr/bin/env python3
"""Replay the deterministic financial-table extractor against cached Markdown."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
VALUES_DIR = REPO_ROOT / "microservices" / "values"
if str(VALUES_DIR) not in sys.path:
    sys.path.insert(0, str(VALUES_DIR))

from periods import ReportingPeriod, fy_start_year_from_date, quarter_from_date  # noqa: E402
from quarter_column import extract_facts_from_quarter_column  # noqa: E402
from values_service import canonicalize_facts  # noqa: E402

try:
    from .baseline_from_db import make_label_id
    from .evaluate import load_jsonl
except ImportError:
    from baseline_from_db import make_label_id
    from evaluate import load_jsonl


def replay(
    gold_records: list[dict[str, Any]],
    *,
    parsed_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    catalog = json.loads(
        (REPO_ROOT / "microservices" / "catalog" / "facts.json").read_text(
            encoding="utf-8"
        )
    )
    aliases = {key: key for key in catalog}
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for gold in gold_records:
        key = (
            gold["document_id"],
            gold["company_symbol"],
            gold["period_end"],
            gold["period_type"],
        )
        grouped.setdefault(key, []).append(gold)

    markdown_dir = (
        Path(parsed_dir).resolve()
        if parsed_dir is not None
        else REPO_ROOT / "data" / "parsed"
    )
    predictions: list[dict[str, Any]] = []
    for (document_id, symbol, period_end, period_type), labels in grouped.items():
        markdown_path = markdown_dir / f"{document_id}.md"
        if not markdown_path.is_file():
            for label in labels:
                predictions.append(
                    {
                        "label_id": label["label_id"],
                        "decision": "abstain",
                        "document_id": document_id,
                        "company_symbol": symbol,
                        "fact_code": label["fact_code"],
                        "period_end": period_end,
                        "period_type": period_type,
                        "basis": label["basis"],
                        "confidence": 0.0,
                        "extraction_method": "missing_parsed_document",
                        "has_unresolved_conflict": False,
                    }
                )
            continue
        markdown = markdown_path.read_text(encoding="utf-8")
        period_date = date.fromisoformat(period_end)
        quarter = quarter_from_date(period_date)
        target = ReportingPeriod(
            quarter=quarter,
            fy_start_year=fy_start_year_from_date(period_date),
            quarter_end=period_end,
            period_type=period_type,
        )
        raw = extract_facts_from_quarter_column(
            markdown,
            target=target,
            period_type=period_type,
            fact_keys=set(catalog),
            facts_catalog=catalog,
        )
        rows = canonicalize_facts(
            raw,
            facts_catalog=catalog,
            storage_to_fact=aliases,
        )
        expected_facts = {label["fact_code"] for label in labels}
        emitted_label_ids: set[str] = set()
        for row in rows:
            if row["fact_key"] not in expected_facts:
                continue
            label_id = make_label_id(
                document_id,
                row["fact_key"],
                row.get("period_end") or period_end,
                row["basis"],
                period_type,
            )
            emitted_label_ids.add(label_id)
            predictions.append(
                {
                    "label_id": label_id,
                    "decision": row.get("decision") or "publish",
                    "document_id": document_id,
                    "company_symbol": symbol,
                    "fact_code": row["fact_key"],
                    "value_numeric": row.get("numeric_value"),
                    "value_text": row.get("value_text"),
                    "unit": row.get("unit"),
                    "period_end": row.get("period_end") or period_end,
                    "period_type": period_type,
                    "basis": row["basis"],
                    "source_page": row.get("source_page"),
                    "source_text": row.get("source_text") or row.get("evidence"),
                    "segment": row.get("segment"),
                    "geography": row.get("geography"),
                    "confidence": row.get("confidence"),
                    "extraction_method": row.get("extraction_method"),
                    "has_unresolved_conflict": bool(row.get("has_unresolved_conflict")),
                }
            )
        for label in labels:
            if label["label_id"] in emitted_label_ids:
                continue
            predictions.append(
                {
                    "label_id": label["label_id"],
                    "decision": "abstain",
                    "document_id": document_id,
                    "company_symbol": symbol,
                    "fact_code": label["fact_code"],
                    "period_end": period_end,
                    "period_type": period_type,
                    "basis": label["basis"],
                    "has_unresolved_conflict": False,
                }
            )
    return sorted(predictions, key=lambda row: row["label_id"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--parsed-dir",
        help="Override the parsed-Markdown cache directory (for isolated benchmarks).",
    )
    args = parser.parse_args()
    predictions = replay(load_jsonl(args.gold), parsed_dir=args.parsed_dir)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in predictions),
        encoding="utf-8",
    )
    print(f"Exported {len(predictions)} deterministic predictions to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
