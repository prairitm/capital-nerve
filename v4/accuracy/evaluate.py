#!/usr/bin/env python3
"""Deterministic scorer for Capital Nerve's approved gold labels.

The evaluator intentionally uses only the Python standard library so it can run
in CI without the extraction services or an OpenAI key.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


DECISIONS = {"publish", "review", "abstain"}
TOLERANCE_BY_UNIT = {
    "crore": 0.01,
    "rs": 0.01,
    "rupee": 0.01,
    "rupees": 0.01,
    "%": 0.01,
    "percent": 0.01,
    "percentage": 0.01,
    "count": 0.0,
    "shares": 0.0,
}
COMPARE_FIELDS = (
    "document_id",
    "company_symbol",
    "fact_code",
    "period_end",
    "period_type",
    "basis",
    "unit",
    "segment",
    "geography",
)


class EvaluationInputError(ValueError):
    """Raised when benchmark inputs are ambiguous or malformed."""


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvaluationInputError(
                    f"{path}:{line_number}: invalid JSON: {exc.msg}"
                ) from exc
            if not isinstance(value, dict):
                raise EvaluationInputError(
                    f"{path}:{line_number}: each line must be a JSON object"
                )
            records.append(value)
    return records


def _index_unique(
    records: Iterable[dict[str, Any]], *, source: str
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for position, record in enumerate(records, 1):
        label_id = record.get("label_id")
        if not isinstance(label_id, str) or not label_id.strip():
            raise EvaluationInputError(
                f"{source} record {position}: label_id must be a non-empty string"
            )
        if label_id in indexed:
            raise EvaluationInputError(f"{source}: duplicate label_id {label_id!r}")
        indexed[label_id] = record
    return indexed


def _validate_gold(record: dict[str, Any]) -> None:
    required = {
        "label_id",
        "document_id",
        "company_symbol",
        "fact_code",
        "unit",
        "period_end",
        "period_type",
        "basis",
        "source_page",
        "source_text",
        "label_status",
    }
    missing = sorted(required - record.keys())
    if missing:
        raise EvaluationInputError(
            f"gold {record.get('label_id', '<unknown>')}: missing {', '.join(missing)}"
        )
    has_numeric = isinstance(record.get("value_numeric"), (int, float)) and not isinstance(
        record.get("value_numeric"), bool
    )
    has_text = isinstance(record.get("value_text"), str) and bool(
        record.get("value_text", "").strip()
    )
    if has_numeric == has_text:
        raise EvaluationInputError(
            f"gold {record['label_id']}: provide exactly one of value_numeric or value_text"
        )
    if not isinstance(record["source_page"], int) or record["source_page"] < 1:
        raise EvaluationInputError(
            f"gold {record['label_id']}: source_page must be a positive integer"
        )


def _validate_prediction(record: dict[str, Any]) -> None:
    decision = record.get("decision")
    if decision not in DECISIONS:
        raise EvaluationInputError(
            f"prediction {record.get('label_id', '<unknown>')}: decision must be one of "
            + ", ".join(sorted(DECISIONS))
        )
    if decision != "publish":
        return
    required = {
        "document_id",
        "company_symbol",
        "fact_code",
        "unit",
        "period_end",
        "period_type",
        "basis",
        "source_page",
        "source_text",
    }
    missing = sorted(required - record.keys())
    if missing:
        raise EvaluationInputError(
            f"prediction {record['label_id']}: published record missing "
            + ", ".join(missing)
        )
    if record.get("value_numeric") is None and not record.get("value_text"):
        raise EvaluationInputError(
            f"prediction {record['label_id']}: published record has no value"
        )


def _normalise_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _tolerance(unit: Any) -> float:
    return TOLERANCE_BY_UNIT.get(_normalise_text(unit), 0.0)


def _numbers_in_text(text: str) -> list[float]:
    values: list[float] = []
    pattern = re.compile(r"(?<![\w.])\(?-?\d[\d,]*(?:\.\d+)?\)?")
    for match in pattern.finditer(text):
        token = match.group(0)
        negative = token.startswith("(") and token.endswith(")")
        token = token.strip("()").replace(",", "")
        try:
            value = float(token)
        except ValueError:
            continue
        values.append(-value if negative else value)
    return values


def _numeric_equal(expected: Any, actual: Any, unit: Any) -> bool:
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return False
    if isinstance(expected, bool) or not isinstance(expected, (int, float)):
        return False
    if not math.isfinite(float(expected)) or not math.isfinite(float(actual)):
        return False
    return math.isclose(
        float(expected), float(actual), rel_tol=0.0, abs_tol=_tolerance(unit)
    )


def _value_equal(gold: dict[str, Any], prediction: dict[str, Any]) -> bool:
    if gold.get("value_numeric") is not None:
        return _numeric_equal(
            gold["value_numeric"], prediction.get("value_numeric"), gold.get("unit")
        )
    return _normalise_text(gold.get("value_text")) == _normalise_text(
        prediction.get("value_text")
    )


def _evidence_supports_value(prediction: dict[str, Any]) -> bool:
    source_text = prediction.get("source_text")
    if not isinstance(source_text, str) or not source_text.strip():
        return False
    numeric = prediction.get("value_numeric")
    if numeric is not None:
        return any(
            _numeric_equal(numeric, candidate, prediction.get("unit"))
            for candidate in _numbers_in_text(source_text)
        )
    value_text = _normalise_text(prediction.get("value_text"))
    return bool(value_text) and value_text in _normalise_text(source_text)


def _published_errors(
    gold: dict[str, Any], prediction: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    for field in COMPARE_FIELDS:
        if _normalise_text(gold.get(field)) != _normalise_text(prediction.get(field)):
            errors.append(f"wrong_{field}")
    if not _value_equal(gold, prediction):
        errors.append("wrong_value")
    if prediction.get("source_page") != gold.get("source_page"):
        errors.append("wrong_source_page")
    if not _evidence_supports_value(prediction):
        errors.append("unsupported_evidence")
    if prediction.get("has_unresolved_conflict") is True:
        errors.append("unresolved_conflict")
    return errors


def evaluate(
    gold_records: Iterable[dict[str, Any]],
    prediction_records: Iterable[dict[str, Any]],
    *,
    include_draft: bool = False,
) -> dict[str, Any]:
    """Score predictions and return a JSON-safe report.

    Draft scoring is for development diagnosis only. It can never pass release
    gates, even if every provisional prediction is correct.
    """

    all_gold = list(gold_records)
    for record in all_gold:
        _validate_gold(record)
    accepted_statuses = {"approved", "draft"} if include_draft else {"approved"}
    scored_gold = [
        record for record in all_gold if record["label_status"] in accepted_statuses
    ]
    gold = _index_unique(scored_gold, source="scored gold")

    all_predictions = list(prediction_records)
    for record in all_predictions:
        _validate_prediction(record)
    predictions = _index_unique(all_predictions, source="predictions")

    counts = Counter()
    errors = Counter()
    per_fact: dict[str, Counter[str]] = defaultdict(Counter)
    details: list[dict[str, Any]] = []

    for label_id, expected in gold.items():
        fact = expected["fact_code"]
        per_fact[fact]["gold"] += 1
        prediction = predictions.get(label_id)
        if prediction is None:
            counts["missing"] += 1
            counts["abstain"] += 1
            per_fact[fact]["abstain"] += 1
            details.append({"label_id": label_id, "decision": "missing", "errors": ["missing_prediction"]})
            continue

        decision = prediction["decision"]
        counts[decision] += 1
        per_fact[fact][decision] += 1
        if decision != "publish":
            details.append({"label_id": label_id, "decision": decision, "errors": []})
            continue

        found_errors = _published_errors(expected, prediction)
        if found_errors:
            counts["incorrect_published"] += 1
            per_fact[fact]["incorrect_published"] += 1
            errors.update(found_errors)
        else:
            counts["correct_published"] += 1
            per_fact[fact]["correct_published"] += 1
        details.append(
            {"label_id": label_id, "decision": decision, "errors": found_errors}
        )

    spurious_ids = sorted(set(predictions) - set(gold))
    spurious_published = sum(
        predictions[label_id]["decision"] == "publish" for label_id in spurious_ids
    )
    counts["spurious_published"] = spurious_published
    errors["spurious_prediction"] = spurious_published

    gold_count = len(gold)
    published = counts["publish"] + spurious_published
    correct = counts["correct_published"]
    precision = correct / published if published else None
    coverage = counts["publish"] / gold_count if gold_count else None
    recall = correct / gold_count if gold_count else None

    per_fact_report: dict[str, dict[str, Any]] = {}
    for fact, fact_counts in sorted(per_fact.items()):
        fact_published = fact_counts["publish"]
        fact_gold = fact_counts["gold"]
        per_fact_report[fact] = {
            **dict(fact_counts),
            "precision": (
                fact_counts["correct_published"] / fact_published
                if fact_published
                else None
            ),
            "recall": fact_counts["correct_published"] / fact_gold,
        }

    release_gates = {
        "approved_gold_only": not include_draft,
        "has_approved_gold": gold_count > 0,
        "has_published_predictions": published > 0,
        "published_precision_100_percent": precision == 1.0,
        "zero_wrong_period": errors["wrong_period_end"] == 0
        and errors["wrong_period_type"] == 0,
        "zero_wrong_basis": errors["wrong_basis"] == 0,
        "zero_wrong_unit": errors["wrong_unit"] == 0,
        "zero_invalid_evidence": errors["wrong_source_page"] == 0
        and errors["unsupported_evidence"] == 0,
        "zero_unresolved_conflicts": errors["unresolved_conflict"] == 0,
        "zero_spurious_published": spurious_published == 0,
    }
    release_gates["passed"] = all(release_gates.values())

    return {
        "provisional": include_draft,
        "approved_gold_records": gold_count,
        "ignored_unapproved_gold_records": len(all_gold) - len(scored_gold),
        "prediction_records": len(predictions),
        "counts": dict(counts),
        "metrics": {
            "auto_published_precision": precision,
            "auto_published_coverage": coverage,
            "recall": recall,
            "review_rate": counts["review"] / gold_count if gold_count else None,
            "abstention_rate": counts["abstain"] / gold_count if gold_count else None,
        },
        "errors": dict(errors),
        "per_fact": per_fact_report,
        "release_gates": release_gates,
        "details": details,
        "spurious_label_ids": spurious_ids,
    }


def _format_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def print_summary(report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    print(f"Approved gold facts: {report['approved_gold_records']}")
    print(f"Predictions: {report['prediction_records']}")
    print(f"Published precision: {_format_percent(metrics['auto_published_precision'])}")
    print(f"Published coverage: {_format_percent(metrics['auto_published_coverage'])}")
    print(f"Recall: {_format_percent(metrics['recall'])}")
    print(f"Review rate: {_format_percent(metrics['review_rate'])}")
    print(f"Abstention rate: {_format_percent(metrics['abstention_rate'])}")
    print(f"Release gates: {'PASS' if report['release_gates']['passed'] else 'FAIL'}")
    if report["errors"]:
        print("Errors:")
        for name, count in sorted(report["errors"].items()):
            if count:
                print(f"  {name}: {count}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True, help="Approved/draft gold JSONL")
    parser.add_argument("--predictions", required=True, help="Prediction JSONL")
    parser.add_argument("--output", help="Optional path for the full JSON report")
    parser.add_argument(
        "--include-draft",
        action="store_true",
        help="Score draft labels provisionally; release gates are forced to fail",
    )
    parser.add_argument(
        "--require-gates",
        action="store_true",
        help="Exit non-zero unless every release gate passes",
    )
    args = parser.parse_args(argv)

    try:
        report = evaluate(
            load_jsonl(args.gold),
            load_jsonl(args.predictions),
            include_draft=args.include_draft,
        )
    except EvaluationInputError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    print_summary(report)
    if args.output:
        Path(args.output).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if args.require_gates and not report["release_gates"]["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
