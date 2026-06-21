"""SQLite persistence for Capital Nerve — stores validated facts and fired signals."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from periods import format_fy_label, format_quarterly_label, prior_quarter

NO_MATERIAL_SIGNAL = "no_material_change"
_SEVERITY_RANK = {"watch": 2, "info": 1}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FactStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        needs_fy_migration = False
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS filings (
                    document_id TEXT PRIMARY KEY,
                    company_ticker TEXT NOT NULL,
                    sha256 TEXT NOT NULL UNIQUE,
                    title TEXT,
                    quarter INTEGER,
                    fy_start_year INTEGER,
                    fy_label TEXT,
                    quarter_end TEXT,
                    ingested_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fact_values (
                    company_ticker TEXT NOT NULL,
                    quarter INTEGER NOT NULL,
                    fy_start_year INTEGER NOT NULL,
                    fy_label TEXT NOT NULL,
                    quarter_end TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    basis TEXT NOT NULL DEFAULT 'consolidated',
                    numeric_value REAL NOT NULL,
                    unit TEXT,
                    evidence TEXT,
                    source_document_id TEXT,
                    status TEXT NOT NULL DEFAULT 'accepted',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (company_ticker, quarter, fy_start_year, fact_key, basis)
                );

                CREATE INDEX IF NOT EXISTS idx_fact_values_company_period
                    ON fact_values (company_ticker, fy_start_year, quarter);

                CREATE TABLE IF NOT EXISTS signal_firings (
                    company_ticker TEXT NOT NULL,
                    quarter INTEGER NOT NULL,
                    fy_start_year INTEGER NOT NULL,
                    fy_label TEXT NOT NULL,
                    quarter_end TEXT NOT NULL,
                    basis TEXT NOT NULL DEFAULT 'consolidated',
                    signal_key TEXT NOT NULL,
                    headline TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    category TEXT,
                    direction TEXT,
                    metric_keys TEXT NOT NULL,
                    trigger_values TEXT,
                    metric_snapshots TEXT,
                    rule_json TEXT,
                    rule_text TEXT,
                    catalog_version TEXT NOT NULL,
                    source_document_id TEXT,
                    is_primary INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'fired',
                    fired_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (company_ticker, quarter, fy_start_year, signal_key, basis)
                );

                CREATE INDEX IF NOT EXISTS idx_signal_firings_company_period
                    ON signal_firings (company_ticker, fy_start_year, quarter);

                CREATE INDEX IF NOT EXISTS idx_signal_firings_signal_key
                    ON signal_firings (signal_key);
                """
            )
            self._ensure_column(conn, "signal_firings", "metric_snapshots", "TEXT")
            self._ensure_column(conn, "signal_firings", "rule_json", "TEXT")
            self._ensure_column(conn, "signal_firings", "rule_text", "TEXT")
            if self._table_has_column(conn, "fact_values", "fiscal_year") and not self._table_has_column(
                conn, "fact_values", "fy_start_year"
            ):
                needs_fy_migration = True

        if needs_fy_migration:
            from scripts.migrate_fy_format import migrate

            migrate(self.db_path)

    @staticmethod
    def _table_has_column(
        conn: sqlite3.Connection, table: str, column: str
    ) -> bool:
        return column in {
            row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def filing_exists(self, sha256: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM filings WHERE sha256 = ?", (sha256,)
            ).fetchone()
        return row is not None

    def upsert_filing(
        self,
        *,
        document_id: str,
        company_ticker: str,
        sha256: str,
        title: str | None,
        quarter: int | None,
        fy_start_year: int | None,
        quarter_end: str | None,
        ingested_at: str,
        fy_label: str | None = None,
    ) -> None:
        if fy_start_year is not None and fy_label is None:
            fy_label = format_fy_label(fy_start_year)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO filings (
                    document_id, company_ticker, sha256, title,
                    quarter, fy_start_year, fy_label, quarter_end, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sha256) DO UPDATE SET
                    document_id = excluded.document_id,
                    title = excluded.title,
                    quarter = excluded.quarter,
                    fy_start_year = excluded.fy_start_year,
                    fy_label = excluded.fy_label,
                    quarter_end = excluded.quarter_end,
                    ingested_at = excluded.ingested_at
                """,
                (
                    document_id,
                    company_ticker,
                    sha256,
                    title,
                    quarter,
                    fy_start_year,
                    fy_label,
                    quarter_end,
                    ingested_at,
                ),
            )

    def upsert_fact(
        self,
        *,
        company_ticker: str,
        quarter: int,
        fy_start_year: int,
        quarter_end: str,
        fact_key: str,
        basis: str,
        numeric_value: float,
        unit: str | None,
        evidence: str | None,
        source_document_id: str | None,
        status: str = "accepted",
        fy_label: str | None = None,
    ) -> None:
        label = fy_label or format_fy_label(fy_start_year)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fact_values (
                    company_ticker, quarter, fy_start_year, fy_label, quarter_end,
                    fact_key, basis, numeric_value, unit, evidence,
                    source_document_id, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_ticker, quarter, fy_start_year, fact_key, basis)
                DO UPDATE SET
                    fy_label = excluded.fy_label,
                    quarter_end = excluded.quarter_end,
                    numeric_value = excluded.numeric_value,
                    unit = excluded.unit,
                    evidence = excluded.evidence,
                    source_document_id = excluded.source_document_id,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    company_ticker,
                    quarter,
                    fy_start_year,
                    label,
                    quarter_end,
                    fact_key,
                    basis,
                    numeric_value,
                    unit,
                    evidence,
                    source_document_id,
                    status,
                    _now_iso(),
                ),
            )

    def load_facts(
        self,
        company_ticker: str,
        quarter: int,
        fy_start_year: int,
        basis: str,
    ) -> dict[str, float]:
        return {
            k: v["numeric_value"]
            for k, v in self.load_fact_details(
                company_ticker, quarter, fy_start_year, basis
            ).items()
        }

    def load_fact_details(
        self,
        company_ticker: str,
        quarter: int,
        fy_start_year: int,
        basis: str,
    ) -> dict[str, dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT fact_key, numeric_value, unit, evidence, source_document_id
                FROM fact_values
                WHERE company_ticker = ? AND quarter = ? AND fy_start_year = ?
                  AND basis = ? AND status = 'accepted'
                """,
                (company_ticker, quarter, fy_start_year, basis),
            ).fetchall()
        return {
            row["fact_key"]: {
                "numeric_value": float(row["numeric_value"]),
                "unit": row["unit"],
                "evidence": row["evidence"],
                "source_document_id": row["source_document_id"],
            }
            for row in rows
        }

    def load_fact_detail(
        self,
        company_ticker: str,
        quarter: int,
        fy_start_year: int,
        basis: str,
        fact_key: str,
    ) -> dict[str, Any] | None:
        return self.load_fact_details(
            company_ticker, quarter, fy_start_year, basis
        ).get(fact_key)

    def get_trend(
        self,
        company_ticker: str,
        fact_key: str,
        basis: str,
        *,
        n: int = 4,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT quarter, fy_start_year, fy_label, quarter_end, numeric_value, unit,
                       evidence, source_document_id
                FROM fact_values
                WHERE company_ticker = ? AND fact_key = ? AND basis = ?
                  AND status = 'accepted'
                ORDER BY quarter_end DESC
                LIMIT ?
                """,
                (company_ticker, fact_key, basis, n),
            ).fetchall()
        return [
            {
                "label": format_quarterly_label(row["quarter"], row["fy_start_year"]),
                "quarter": row["quarter"],
                "fy_start_year": row["fy_start_year"],
                "fy_label": row["fy_label"],
                "quarter_end": row["quarter_end"],
                "value": float(row["numeric_value"]),
                "unit": row["unit"],
                "evidence": row["evidence"],
                "source": "database",
                "source_document_id": row["source_document_id"],
            }
            for row in reversed(rows)
        ]

    def get_trend_alias_aware(
        self,
        company_ticker: str,
        fact_key: str,
        basis: str,
        *,
        n: int = 4,
    ) -> list[dict[str, Any]]:
        """Like get_trend but tries catalog fact aliases and standalone fallback."""
        from catalog_loader import canonical_fact_key, fact_lookup_keys, get_catalog

        catalog = get_catalog()
        canonical = canonical_fact_key(fact_key) or fact_key
        keys = (
            fact_lookup_keys(canonical)
            if canonical in catalog.facts
            else [fact_key]
        )
        for key in keys:
            series = self.get_trend(company_ticker, key, basis, n=n)
            if series:
                return series
        if basis == "consolidated":
            for key in keys:
                series = self.get_trend(company_ticker, key, "standalone", n=n)
                if series:
                    return series
        return []

    def list_periods(
        self, company_ticker: str, basis: str | None = None
    ) -> list[dict[str, Any]]:
        query = """
            SELECT DISTINCT quarter, fy_start_year, fy_label, quarter_end
            FROM fact_values
            WHERE company_ticker = ? AND status = 'accepted'
        """
        params: list[Any] = [company_ticker]
        if basis:
            query += " AND basis = ?"
            params.append(basis)
        query += " ORDER BY quarter_end ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "quarter": row["quarter"],
                "fy_start_year": row["fy_start_year"],
                "fy_label": row["fy_label"],
                "quarter_end": row["quarter_end"],
                "label": format_quarterly_label(row["quarter"], row["fy_start_year"]),
            }
            for row in rows
        ]

    def latest_period(
        self, company_ticker: str, basis: str | None = None
    ) -> dict[str, Any] | None:
        periods = self.list_periods(company_ticker, basis)
        return periods[-1] if periods else None

    def _filing_document_id(
        self,
        company_ticker: str,
        quarter: int,
        fy_start_year: int,
    ) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT document_id FROM filings
                WHERE company_ticker = ? AND quarter = ? AND fy_start_year = ?
                ORDER BY ingested_at DESC
                LIMIT 1
                """,
                (company_ticker, quarter, fy_start_year),
            ).fetchone()
        return row["document_id"] if row else None

    @staticmethod
    def _metrics_by_key(metrics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        from catalog_engine import catalog_metric_key

        by_key: dict[str, dict[str, Any]] = {}
        for metric in metrics:
            metric_key = metric.get("metric_key")
            if not metric_key:
                continue
            by_key[metric_key] = metric
            canonical = catalog_metric_key(metric_key)
            by_key.setdefault(canonical, metric)
        return by_key

    @staticmethod
    def _trigger_values(
        metric_keys: list[str], metrics: list[dict[str, Any]]
    ) -> dict[str, float]:
        by_key = FactStore._metrics_by_key(metrics)
        return {
            mk: float(by_key[mk]["value"])
            for mk in metric_keys
            if mk in by_key and by_key[mk].get("value") is not None
        }

    def _metric_snapshots(
        self,
        metric_keys: list[str],
        metrics: list[dict[str, Any]],
        *,
        company_ticker: str,
        quarter: int,
        fy_start_year: int,
        basis: str,
    ) -> dict[str, dict[str, Any]]:
        """Capture computed metric values and underlying fact inputs at fire time."""
        from catalog_engine import ScopeContext, catalog_metric_key
        from catalog_loader import get_catalog

        catalog = get_catalog()
        by_key = self._metrics_by_key(metrics)
        current = self.load_fact_details(company_ticker, quarter, fy_start_year, basis)
        prior_year = self.load_fact_details(
            company_ticker, quarter, fy_start_year - 1, basis
        )
        pq, pfy = prior_quarter(quarter, fy_start_year)
        prior_quarter_details = self.load_fact_details(company_ticker, pq, pfy, basis)
        ctx = ScopeContext.from_fact_details(current, prior_year, prior_quarter_details)

        snapshots: dict[str, dict[str, Any]] = {}
        for metric_key in metric_keys:
            spec_key = catalog_metric_key(metric_key)
            spec = catalog.metrics.get(spec_key)
            metric = by_key.get(metric_key) or by_key.get(spec_key)
            if spec is None and metric is None:
                continue

            value = metric.get("value") if metric else None
            inputs: list[dict[str, Any]] = []
            for inp in (spec or {}).get("inputs") or []:
                fact_key = inp["fact_key"]
                scope = inp["scope"]
                resolved = ctx.comparable_fact_value(fact_key, scope)
                if resolved is None:
                    resolved = ctx.fact_value(fact_key, scope)
                detail: dict[str, Any] = {
                    "var": inp["var"],
                    "fact_key": fact_key,
                    "scope": scope,
                    "value": resolved,
                }
                if metric:
                    for row in metric.get("input_details") or []:
                        if row.get("fact_key") != fact_key:
                            continue
                        role_scope = {
                            "current": "CURRENT",
                            "prior_year": "PY",
                            "prior_quarter": "PQ",
                        }.get(row.get("role", ""), "")
                        if role_scope and role_scope != scope.upper():
                            continue
                        if row.get("value") is not None:
                            detail["value"] = row["value"]
                        if row.get("unit") is not None:
                            detail["unit"] = row["unit"]
                        if row.get("evidence") is not None:
                            detail["evidence"] = row["evidence"]
                        if row.get("source_document_id") is not None:
                            detail["source_document_id"] = row["source_document_id"]
                        break
                inputs.append(detail)

            snapshots[metric_key] = {
                "value": float(value) if value is not None else None,
                "formula": (metric or {}).get("formula_evaluated")
                or (spec or {}).get("formula"),
                "unit": (metric or {}).get("unit") or (spec or {}).get("unit"),
                "inputs": inputs,
            }
        return snapshots

    @staticmethod
    def _resolve_signal_rule(signal: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        from catalog_engine import format_rule_text
        from catalog_loader import get_catalog

        rule = signal.get("rule")
        if rule is None:
            spec = get_catalog().signals.get(signal["signal_key"], {})
            rule = spec.get("rule")
        if not rule:
            return None, None
        rule_text = signal.get("rule_text") or format_rule_text(rule)
        return rule, rule_text

    @staticmethod
    def _primary_signal_key(signals: list[dict[str, Any]]) -> str | None:
        material = [
            s for s in signals if s.get("signal_key") != NO_MATERIAL_SIGNAL
        ]
        if not material:
            return None
        return max(
            material,
            key=lambda s: _SEVERITY_RANK.get(s.get("severity", ""), 0),
        )["signal_key"]

    def persist_period_signals(
        self,
        *,
        company_ticker: str,
        quarter: int,
        fy_start_year: int,
        quarter_end: str,
        basis: str,
        signals: list[dict[str, Any]],
        metrics: list[dict[str, Any]],
        catalog_version: str,
        source_document_id: str | None = None,
        fy_label: str | None = None,
    ) -> dict[str, Any]:
        """Upsert fired signals for a period; drop stale rows no longer firing."""
        label = fy_label or format_fy_label(fy_start_year)
        material = [
            s for s in signals if s.get("signal_key") != NO_MATERIAL_SIGNAL
        ]
        source_document_id = source_document_id or self._filing_document_id(
            company_ticker, quarter, fy_start_year
        )
        primary_key = self._primary_signal_key(signals)
        now = _now_iso()
        fired_keys: set[str] = set()

        with self._connect() as conn:
            for signal in material:
                signal_key = signal["signal_key"]
                fired_keys.add(signal_key)
                metric_keys = signal.get("metric_keys") or []
                trigger_values = self._trigger_values(metric_keys, metrics)
                metric_snapshots = self._metric_snapshots(
                    metric_keys,
                    metrics,
                    company_ticker=company_ticker,
                    quarter=quarter,
                    fy_start_year=fy_start_year,
                    basis=basis,
                )
                rule_json, rule_text = self._resolve_signal_rule(signal)
                conn.execute(
                    """
                    INSERT INTO signal_firings (
                        company_ticker, quarter, fy_start_year, fy_label, quarter_end, basis,
                        signal_key, headline, rationale, severity, category, direction,
                        metric_keys, trigger_values, metric_snapshots,
                        rule_json, rule_text, catalog_version,
                        source_document_id, is_primary, status, fired_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(company_ticker, quarter, fy_start_year, signal_key, basis)
                    DO UPDATE SET
                        fy_label = excluded.fy_label,
                        quarter_end = excluded.quarter_end,
                        headline = excluded.headline,
                        rationale = excluded.rationale,
                        severity = excluded.severity,
                        category = excluded.category,
                        direction = excluded.direction,
                        metric_keys = excluded.metric_keys,
                        trigger_values = excluded.trigger_values,
                        metric_snapshots = excluded.metric_snapshots,
                        rule_json = excluded.rule_json,
                        rule_text = excluded.rule_text,
                        catalog_version = excluded.catalog_version,
                        source_document_id = excluded.source_document_id,
                        is_primary = excluded.is_primary,
                        status = excluded.status,
                        updated_at = excluded.updated_at
                    """,
                    (
                        company_ticker,
                        quarter,
                        fy_start_year,
                        label,
                        quarter_end,
                        basis,
                        signal_key,
                        signal["headline"],
                        signal["rationale"],
                        signal["severity"],
                        signal.get("category"),
                        signal.get("direction"),
                        json.dumps(metric_keys),
                        json.dumps(trigger_values) if trigger_values else None,
                        json.dumps(metric_snapshots) if metric_snapshots else None,
                        json.dumps(rule_json) if rule_json else None,
                        rule_text,
                        catalog_version,
                        source_document_id,
                        1 if signal_key == primary_key else 0,
                        "fired",
                        now,
                        now,
                    ),
                )

            if fired_keys:
                placeholders = ",".join("?" for _ in fired_keys)
                conn.execute(
                    f"""
                    DELETE FROM signal_firings
                    WHERE company_ticker = ? AND quarter = ? AND fy_start_year = ?
                      AND basis = ? AND signal_key NOT IN ({placeholders})
                    """,
                    (company_ticker, quarter, fy_start_year, basis, *fired_keys),
                )
            else:
                conn.execute(
                    """
                    DELETE FROM signal_firings
                    WHERE company_ticker = ? AND quarter = ? AND fy_start_year = ?
                      AND basis = ?
                    """,
                    (company_ticker, quarter, fy_start_year, basis),
                )

            if primary_key and fired_keys:
                conn.execute(
                    """
                    UPDATE signal_firings SET is_primary = 0
                    WHERE company_ticker = ? AND quarter = ? AND fy_start_year = ?
                      AND basis = ?
                    """,
                    (company_ticker, quarter, fy_start_year, basis),
                )
                conn.execute(
                    """
                    UPDATE signal_firings SET is_primary = 1
                    WHERE company_ticker = ? AND quarter = ? AND fy_start_year = ?
                      AND basis = ? AND signal_key = ?
                    """,
                    (
                        company_ticker,
                        quarter,
                        fy_start_year,
                        basis,
                        primary_key,
                    ),
                )

        return {
            "company_ticker": company_ticker,
            "persisted_count": len(material),
            "signal_keys": sorted(fired_keys),
            "primary_signal_key": primary_key,
        }

    @staticmethod
    def _row_to_signal(row: sqlite3.Row) -> dict[str, Any]:
        metric_keys = json.loads(row["metric_keys"])
        out: dict[str, Any] = {
            "signal_key": row["signal_key"],
            "severity": row["severity"],
            "headline": row["headline"],
            "rationale": row["rationale"],
            "metric_keys": metric_keys,
            "category": row["category"],
            "direction": row["direction"],
        }
        if row["trigger_values"]:
            out["trigger_values"] = json.loads(row["trigger_values"])
        if "metric_snapshots" in row.keys() and row["metric_snapshots"]:
            out["metric_snapshots"] = json.loads(row["metric_snapshots"])
        if "rule_json" in row.keys() and row["rule_json"]:
            out["rule"] = json.loads(row["rule_json"])
        if "rule_text" in row.keys() and row["rule_text"]:
            out["rule_text"] = row["rule_text"]
        return out

    def load_signals(
        self,
        company_ticker: str,
        quarter: int,
        fy_start_year: int,
        basis: str,
    ) -> list[dict[str, Any]] | None:
        """Return persisted signals for a period, or None if never evaluated."""
        with self._connect() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT signal_key, headline, rationale, severity, category,
                           direction, metric_keys, trigger_values, metric_snapshots,
                           rule_json, rule_text, is_primary, fired_at
                    FROM signal_firings
                    WHERE company_ticker = ? AND quarter = ? AND fy_start_year = ?
                      AND basis = ? AND status = 'fired'
                    ORDER BY is_primary DESC, severity DESC, signal_key ASC
                    """,
                    (company_ticker, quarter, fy_start_year, basis),
                ).fetchall()
            except sqlite3.OperationalError:
                return None
        if not rows:
            return None
        return [self._row_to_signal(row) for row in rows]

    def list_signal_periods(
        self, company_ticker: str, basis: str | None = None
    ) -> list[dict[str, Any]]:
        query = """
            SELECT DISTINCT quarter, fy_start_year, fy_label, quarter_end
            FROM signal_firings
            WHERE company_ticker = ? AND status = 'fired'
        """
        params: list[Any] = [company_ticker]
        if basis:
            query += " AND basis = ?"
            params.append(basis)
        query += " ORDER BY quarter_end ASC"
        with self._connect() as conn:
            try:
                rows = conn.execute(query, params).fetchall()
            except sqlite3.OperationalError:
                return []
        return [
            {
                "quarter": row["quarter"],
                "fy_start_year": row["fy_start_year"],
                "fy_label": row["fy_label"],
                "quarter_end": row["quarter_end"],
                "label": format_quarterly_label(row["quarter"], row["fy_start_year"]),
            }
            for row in rows
        ]
