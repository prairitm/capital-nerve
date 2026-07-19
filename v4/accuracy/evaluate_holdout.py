#!/usr/bin/env python3
"""Evaluate the locked holdout only in explicit release mode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluate import evaluate, load_jsonl, print_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-evaluation", action="store_true")
    parser.add_argument("--manifest", default="accuracy/holdout/manifest.json")
    parser.add_argument("--gold-dir", default="accuracy/holdout/gold")
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not args.release_evaluation:
        parser.error("--release-evaluation is required for locked holdout access")

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if len(manifest.get("candidates", [])) != 10:
        parser.error("holdout manifest must contain exactly 10 candidates")
    if any(not row.get("document_id") for row in manifest["candidates"]):
        parser.error("holdout is not materialized by the independent labeler")
    gold_paths = sorted(Path(args.gold_dir).glob("*.jsonl"))
    if not gold_paths:
        parser.error("no independently labeled holdout gold files exist")
    gold = [row for path in gold_paths for row in load_jsonl(path)]
    if any(row.get("label_status") != "approved" for row in gold):
        parser.error("all holdout labels must be independently approved")

    report = evaluate(gold, load_jsonl(args.predictions), include_draft=False)
    Path(args.output).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print_summary(report)
    return 0 if report["release_gates"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
