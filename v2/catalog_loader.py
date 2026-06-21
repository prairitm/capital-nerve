"""Load and validate the v2 JSON catalog (facts, metrics, signals)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"


@dataclass(frozen=True)
class Catalog:
    version: str
    facts: dict[str, dict[str, Any]]
    metrics: dict[str, dict[str, Any]]
    signals: dict[str, dict[str, Any]]
    storage_to_fact: dict[str, str]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must be a JSON object")
    return data


def _build_storage_index(facts: dict[str, dict[str, Any]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for key, spec in facts.items():
        index[key] = key
        for alias in spec.get("aliases") or []:
            index[str(alias)] = key
    return index


def load_catalog(*, reload: bool = False) -> Catalog:
    if reload:
        get_catalog.cache_clear()

    manifest_path = CATALOG_DIR / "manifest.json"
    manifest = _read_json(manifest_path)
    version = str(manifest.get("catalog_version", "0"))

    facts = _read_json(CATALOG_DIR / "facts.json")
    metrics = _read_json(CATALOG_DIR / "metrics.json")
    signals = _read_json(CATALOG_DIR / "signals.json")

    for name, blob in (("facts", facts), ("metrics", metrics), ("signals", signals)):
        for code, spec in blob.items():
            if not isinstance(spec, dict):
                raise ValueError(f"{name}.{code} must be an object")

    return Catalog(
        version=version,
        facts=facts,
        metrics=metrics,
        signals=signals,
        storage_to_fact=_build_storage_index(facts),
    )


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    return load_catalog()


def allowed_extraction_keys() -> list[str]:
    """Keys the extraction schema may emit (canonical fact_key values + aliases)."""
    catalog = get_catalog()
    keys: list[str] = []
    for key, spec in catalog.facts.items():
        keys.append(key)
        keys.extend(spec.get("aliases") or [])
    return sorted(set(keys))


def fact_lookup_keys(fact_key: str) -> list[str]:
    spec = get_catalog().facts[fact_key]
    return [fact_key, *(spec.get("aliases") or [])]


def canonical_fact_key(storage_key: str) -> str | None:
    return get_catalog().storage_to_fact.get(storage_key)


def signal_categories() -> dict[str, str]:
    return {code: spec["category"] for code, spec in get_catalog().signals.items()}


def signal_directions() -> dict[str, str]:
    return {code: spec["direction"] for code, spec in get_catalog().signals.items()}


def fact_meta_for_mapper() -> dict[str, tuple[str, str, str]]:
    """fact_key -> (v1 line_item_code, display name, unit) for serve/mapper.py."""
    catalog = get_catalog()
    out: dict[str, tuple[str, str, str]] = {}
    for key, spec in catalog.facts.items():
        unit = spec.get("unit") or ""
        out[key] = (key, spec.get("name", key), unit)
        for alias in spec.get("aliases") or []:
            out[alias] = (key, spec.get("name", key), unit)
    return out


def metric_meta_for_mapper() -> dict[str, tuple[str, str, str]]:
    """metric_key -> (v1 metric_code, display name, unit) for serve/mapper.py."""
    catalog = get_catalog()
    out: dict[str, tuple[str, str, str]] = {}
    for key, spec in catalog.metrics.items():
        unit = spec.get("unit") or ""
        out[key] = (key, spec.get("name", key), unit)
    return out
