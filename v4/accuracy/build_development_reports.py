#!/usr/bin/env python3
"""Build frozen aggregate development predictions, metrics, and breakdowns."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from evaluate import evaluate, load_jsonl


ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"

ORIGINAL_STEMS = (
    "kec_2024_fy",
    "kec_2024_9m",
    "lt_2025_q2",
    "lt_2025_9m",
    "reliance_2025_q1",
    "reliance_2025_h1",
    "tcs_2026_q1",
)
NEW_STEMS = (
    "infy_2025_q1_newspaper",
    "itc_2025_q1",
    "maruti_2025_q1",
    "ultracemco_2025_q1",
    "asianpaint_2025_q1",
    "drreddy_2025_q1",
    "hindunilvr_2025_q1",
    "tatasteel_2025_q1",
    "bhartiartl_2025_q1",
    "sunpharma_2025_q1",
    "infy_2025_q4_fy",
    "itc_2025_q4_fy",
)
BASELINE_NAMES = {
    "infy_2025_q1_newspaper": "infy_2025_q1_newspaper_baseline_predictions.jsonl",
    "itc_2025_q1": "itc_2025_q1_baseline_predictions.jsonl",
    "maruti_2025_q1": "maruti_2025_q1_baseline_predictions.jsonl",
    "ultracemco_2025_q1": "ultracemco_2025_q1_baseline_predictions.jsonl",
    "asianpaint_2025_q1": "asianpaint_2025_q1_baseline_predictions.jsonl",
    "drreddy_2025_q1": "drreddy_2025_q1_baseline_predictions.jsonl",
    "hindunilvr_2025_q1": "hindunilvr_2025_q1_predictions.jsonl",
    "tatasteel_2025_q1": "tatasteel_2025_q1_baseline_predictions.jsonl",
    "bhartiartl_2025_q1": "bhartiartl_2025_q1_baseline_predictions.jsonl",
    "sunpharma_2025_q1": "sunpharma_2025_q1_baseline_predictions.jsonl",
    "infy_2025_q4_fy": "infy_2025_q4_fy_baseline_predictions.jsonl",
    "itc_2025_q4_fy": "itc_2025_q4_fy_baseline_predictions.jsonl",
}


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in records),
        encoding="utf-8",
    )


def _load_many(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(load_jsonl(path))
    return rows


def _metric_slice(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "gold": report["approved_gold_records"],
        "predictions": report["prediction_records"],
        "counts": report["counts"],
        "metrics": report["metrics"],
        "errors": report["errors"],
    }


def _breakdowns(
    gold: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    by_label = {row["label_id"]: row for row in predictions}
    document_meta = {row["document_id"]: row for row in inventory["documents"]}
    dimensions: dict[str, dict[str, list[dict[str, Any]]]] = {
        name: defaultdict(list)
        for name in (
            "company",
            "document",
            "fact_code",
            "period_type",
            "basis",
            "pdf_difficulty",
            "extraction_method",
        )
    }
    for row in gold:
        prediction = by_label.get(row["label_id"], {})
        meta = document_meta.get(row["document_id"], {})
        values = {
            "company": row["company_symbol"],
            "document": row["document_id"],
            "fact_code": row["fact_code"],
            "period_type": row["period_type"],
            "basis": row["basis"],
            "pdf_difficulty": "difficult" if meta.get("difficult_pdf") else "standard",
            "extraction_method": prediction.get("extraction_method")
            or prediction.get("decision")
            or "missing",
        }
        for dimension, value in values.items():
            dimensions[dimension][str(value)].append(row)

    result: dict[str, Any] = {}
    for dimension, groups in dimensions.items():
        result[dimension] = {}
        for value, subset in sorted(groups.items()):
            label_ids = {row["label_id"] for row in subset}
            subset_predictions = [
                row for row in predictions if row["label_id"] in label_ids
            ]
            result[dimension][value] = _metric_slice(
                evaluate(subset, subset_predictions, include_draft=True)
            )
    return result


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    gold = _load_many(sorted((ROOT / "gold").glob("*.jsonl")))
    inventory = json.loads((ROOT / "benchmark_inventory.json").read_text(encoding="utf-8"))

    # The accepted v0.1 checkpoint is a frozen pre-change artifact. Do not
    # rebuild the before-fix baseline from mutable per-document after-fix
    # replays, or later parser work will silently rewrite history.
    baseline_paths = [REPORTS / "benchmark_v0.1_after_fix_predictions.jsonl"] + [
        REPORTS / BASELINE_NAMES[stem] for stem in NEW_STEMS
    ]
    baseline_paths.append(
        REPORTS / "sunpharma_newspaper_negative_control_baseline_predictions.jsonl"
    )
    after_paths = [
        REPORTS / f"{stem}_after_fix_predictions.jsonl"
        for stem in (*ORIGINAL_STEMS, *NEW_STEMS)
    ]
    for path in (*baseline_paths, *after_paths):
        if not path.is_file():
            raise FileNotFoundError(path)

    before = _load_many(baseline_paths)
    after = _load_many(after_paths)
    original_gold = _load_many(ROOT / "gold" / f"{stem}.jsonl" for stem in ORIGINAL_STEMS)
    new_gold = _load_many(ROOT / "gold" / f"{stem}.jsonl" for stem in NEW_STEMS)
    original_after = _load_many(after_paths[: len(ORIGINAL_STEMS)])
    new_after = _load_many(after_paths[len(ORIGINAL_STEMS) :])
    _write_jsonl(REPORTS / "development_gold_draft.jsonl", gold)
    _write_jsonl(REPORTS / "development_before_fix_predictions.jsonl", before)
    _write_jsonl(REPORTS / "development_after_fix_predictions.jsonl", after)
    _write_jsonl(REPORTS / "original_150_gold_draft.jsonl", original_gold)
    _write_jsonl(REPORTS / "original_150_after_fix_predictions.jsonl", original_after)
    _write_jsonl(REPORTS / "new_278_gold_draft.jsonl", new_gold)
    _write_jsonl(REPORTS / "new_278_after_fix_predictions.jsonl", new_after)

    before_report = evaluate(gold, before, include_draft=True)
    after_report = evaluate(gold, after, include_draft=True)
    (REPORTS / "development_before_fix.json").write_text(
        json.dumps(before_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (REPORTS / "development_after_fix.json").write_text(
        json.dumps(after_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (REPORTS / "original_150_after_fix.json").write_text(
        json.dumps(
            evaluate(original_gold, original_after, include_draft=True),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (REPORTS / "new_278_after_fix.json").write_text(
        json.dumps(
            evaluate(new_gold, new_after, include_draft=True),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    breakdowns = {
        "provisional": True,
        "before_fix": _breakdowns(gold, before, inventory),
        "after_fix": _breakdowns(gold, after, inventory),
    }
    (REPORTS / "development_breakdowns.json").write_text(
        json.dumps(breakdowns, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"before": _metric_slice(before_report), "after": _metric_slice(after_report)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
