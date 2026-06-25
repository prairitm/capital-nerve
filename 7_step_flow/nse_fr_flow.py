# %% [markdown]
# ## STEP 1 / 7  -  COMPANY

# %%
# =============================================================================
# STEP 1 / 7  -  COMPANY
# Register the company (keyed by symbol) in the v3 SQLite DB `companies` table.
# =============================================================================
import hashlib
import sqlite3
from pathlib import Path

# --- Config: change these for any NSE-listed symbol ---
import sys
import argparse

parser = argparse.ArgumentParser(description="NSE FR Flow")
parser.add_argument("--symbol", type=str, required=True, help="NSE-listed company symbol")
parser.add_argument("--from_date", type=str, required=True, help="Start date (DD-MM-YYYY)")
parser.add_argument("--to_date", type=str, required=True, help="End date (DD-MM-YYYY)")

args = parser.parse_args()

SYMBOL = args.symbol
FROM_DATE = args.from_date
TO_DATE = args.to_date
EVENT_TYPE = "Financial Results"  # this notebook only handles Financial Results

# --- Paths (resolved relative to this notebook) ---
NOTEBOOK_DIR = Path.cwd()
REPO_ROOT = NOTEBOOK_DIR.parent if NOTEBOOK_DIR.name == "7_step_flow" else NOTEBOOK_DIR
DB_PATH = (REPO_ROOT / "v3" / "data" / "capital_nerve.db").resolve()
CATALOG_DIR = (REPO_ROOT / "v2" / "catalog").resolve()
DOCUMENTS_DIR = (REPO_ROOT / "v3" / "data" / "documents").resolve()
ENV_PATH = (REPO_ROOT / "v3" / ".env").resolve()

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

# Schema bootstrap (mirrors v3/db.py so the notebook works on a fresh DB).
SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, ticker TEXT, exchange TEXT,
    sector TEXT, industry TEXT, isin TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
    event_type TEXT NOT NULL, event_date TEXT NOT NULL, fiscal_year INTEGER,
    fiscal_quarter INTEGER, title TEXT, source_url TEXT, document_id TEXT,
    status TEXT DEFAULT 'processed'
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
    source_url TEXT, storage_path TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
    title TEXT, document_kind TEXT, file_size INTEGER,
    status TEXT DEFAULT 'pending', error_message TEXT,
    ingested_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS extracted_values (
    id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT NOT NULL REFERENCES events(id), value_code TEXT NOT NULL,
    value_numeric REAL, value_text TEXT, unit TEXT, period_type TEXT,
    period_start TEXT, period_end TEXT, basis TEXT DEFAULT 'consolidated',
    segment TEXT, geography TEXT, source_text TEXT, source_page INTEGER,
    confidence REAL
);
CREATE TABLE IF NOT EXISTS metrics (
    id TEXT PRIMARY KEY, metric_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
    formula TEXT, unit TEXT, description TEXT
);
CREATE TABLE IF NOT EXISTS metric_values (
    id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT REFERENCES events(id), metric_id TEXT NOT NULL REFERENCES metrics(id),
    metric_value REAL NOT NULL, period_start TEXT, period_end TEXT, segment TEXT,
    calculation_data TEXT, calculated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT REFERENCES events(id), signal_type TEXT NOT NULL, title TEXT NOT NULL,
    description TEXT, direction TEXT, severity TEXT, confidence REAL, evidence TEXT,
    detected_at TEXT DEFAULT (datetime('now'))
);
"""


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Consistent company id derived from the symbol (kept the same in every step).
company_id = hashlib.sha256(f"{SYMBOL}:NSE".encode()).hexdigest()

with db_connect() as conn:
    conn.executescript(SCHEMA)
    conn.execute(
        """
        INSERT INTO companies (id, name, ticker, exchange)
        VALUES (?, ?, ?, 'NSE')
        ON CONFLICT(id) DO UPDATE SET ticker = excluded.ticker
        """,
        (company_id, SYMBOL, SYMBOL),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()

print(f"DB: {DB_PATH}")
print(f"Registered company {SYMBOL}  (company_id={company_id[:12]}...)")
print(dict(row))

# %% [markdown]
# ## STEP 2 / 7  -  EVENT

# %%
# =============================================================================
# STEP 2 / 7  -  EVENT
# Call the NSE corporate-announcements API for the company over the window,
# backfill company name/ISIN, and persist every announcement as a discovered event.
# =============================================================================
import requests

_API_URL = "https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi"
_HOMEPAGE = "https://www.nseindia.com"
_PAGE_URL = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"

# NSE blocks generic Python user agents without a session cookie.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": _PAGE_URL,
}

params = {
    "functionName": "getCorporateAnnouncement",
    "symbol": SYMBOL,
    "marketApiType": "equities",
    "subject": "",
    "fromDate": FROM_DATE,
    "toDate": TO_DATE,
}

# `session` is reused in Step 4 to download the PDF with the warmed cookies.
session = requests.Session()
session.headers.update(_HEADERS)
session.get(_HOMEPAGE, timeout=30)  # warm up cookies

response = session.get(_API_URL, params=params, timeout=30)
response.raise_for_status()
announcements = response.json()


def event_id_from_source(source_url: str) -> str:
    return hashlib.sha256(f"{company_id}:{source_url}".encode()).hexdigest()


# Backfill company name / ISIN from the first announcement (same company_id).
# The ISIN column is UNIQUE; an earlier (ISIN-keyed) run may already own it, so
# only claim the ISIN when it is free or already ours.
if announcements:
    first = announcements[0]
    isin = first.get("sm_isin")
    with db_connect() as conn:
        if isin:
            owner = conn.execute(
                "SELECT id FROM companies WHERE isin = ?", (isin,)
            ).fetchone()
            if owner is not None and owner["id"] != company_id:
                isin = None  # taken by a different company row -> don't reclaim
        conn.execute(
            """
            UPDATE companies
            SET name = COALESCE(?, name), isin = COALESCE(?, isin),
                industry = COALESCE(?, industry)
            WHERE id = ?
            """,
            (
                first.get("sm_name") or SYMBOL,
                isin,
                first.get("smIndustry"),
                company_id,
            ),
        )
        conn.commit()

# Persist every announcement as a discovered event.
stored = 0
with db_connect() as conn:
    for item in announcements:
        source_url = item.get("attchmntFile") or ""
        seed = source_url or f"{item.get('desc')}:{item.get('dt')}"
        ev_id = event_id_from_source(seed)
        conn.execute(
            """
            INSERT OR IGNORE INTO events (
                id, company_id, event_type, event_date, title, source_url, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'discovered')
            """,
            (
                ev_id,
                company_id,
                (item.get("desc") or "(missing)").strip(),
                (item.get("sort_date") or "")[:10],
                item.get("attchmntText"),
                source_url or None,
            ),
        )
        stored += 1
    conn.commit()

by_desc: dict[str, list[dict]] = {}
for item in announcements:
    desc = (item.get("desc") or "(missing)").strip()
    by_desc.setdefault(desc, []).append(item)

print(f"{len(announcements)} announcements ({stored} stored as events) "
      f"across {len(by_desc)} desc buckets for {SYMBOL} [{FROM_DATE} -> {TO_DATE}]\n")
for desc, items in sorted(by_desc.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    print(f"  {len(items):>3}  {desc}")

# %% [markdown]
# ## STEP 3 / 7  -  EVENT TYPE

# %%
# =============================================================================
# STEP 3 / 7  -  EVENT TYPE
# Classify announcements into the three buckets and keep only Financial Results.
# (Earnings Call Transcript / Investor Presentation are recognised but not handled.)
# Resolve the canonical results PDF by verifying shortlisted candidates.
# =============================================================================
import sys

V3_ROOT = (REPO_ROOT / "v3").resolve()
if str(V3_ROOT) not in sys.path:
    sys.path.insert(0, str(V3_ROOT))

from nse_fr_resolver import infer_period_markers, resolve_canonical_financial_report


def _text_blob(item: dict) -> str:
    parts = [
        item.get("desc") or "",
        item.get("attchmntText") or "",
        item.get("attchmntFile") or "",
    ]
    return " ".join(parts).lower()


def classify_announcement(item: dict) -> str:
    """Trimmed classifier covering the three event-type buckets this flow knows."""
    desc = (item.get("desc") or "").strip()
    blob = _text_blob(item)

    def has(*phrases: str) -> bool:
        return any(p in blob for p in phrases)

    # Earnings call transcript (a results-adjacent doc we recognise but skip).
    if has("transcript of the discussion", "earnings call transcript", "concall transcript"):
        return "Earnings Call Transcript"

    # Investor presentation.
    if desc == "Investor Presentation" or has("investor presentation"):
        return "Investor Presentation"

    # Financial results: the actual results filing, not an intimation/conf-call.
    intimation = has(
        "scheduled to be held", "audio recording", "will hold", "will be held", "informed the exchange regarding board meeting",
        "conference call", "prior intimation", "recording and transcript", "media release", "shareholder meeting"
    )
    if desc == "Financial Results" and not intimation:
        return "Financial Results"
    if has("financial results", "unaudited financial", "audited financial", "outcome of board meeting") and not intimation:
        return "Financial Results"

    return "Other"


# Attach classification + parsed timestamp to each announcement.
from datetime import datetime

for item in announcements:
    item["event_bucket"] = classify_announcement(item)

financial_results = [a for a in announcements if a["event_bucket"] == "Financial Results"]


def _sort_key(item: dict):
    try:
        return datetime.strptime(item.get("sort_date", ""), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.min


financial_results.sort(key=_sort_key, reverse=True)

if not financial_results:
    raise RuntimeError(
        f"No '{EVENT_TYPE}' announcements found for {SYMBOL} in {FROM_DATE} -> {TO_DATE}"
    )

period_markers = infer_period_markers(announcements)
print(f"Resolving canonical financial report ({len(financial_results)} candidate(s), "
      f"{len(period_markers)} period marker(s))...")

resolved_fr = resolve_canonical_financial_report(
    announcements,
    financial_results,
    period_markers=period_markers or None,
    session=session,
    referer=_PAGE_URL,
)
if not resolved_fr:
    raise RuntimeError(
        f"No valid financial results PDF found for {SYMBOL} in {FROM_DATE} -> {TO_DATE}"
    )

chosen = resolved_fr["announcement"]
chosen_source_url = resolved_fr["url"]
event_id = event_id_from_source(chosen_source_url)

# Mark the chosen event row as the selected Financial Result.
with db_connect() as conn:
    conn.execute(
        "UPDATE events SET event_type = ?, status = 'selected' WHERE id = ?",
        (EVENT_TYPE, event_id),
    )
    conn.commit()

print(f"Found {len(financial_results)} Financial Results candidate(s):")
for a in financial_results:
    flag = "  <-- chosen" if a is chosen else ""
    print(f"  {a.get('sort_date')}  {a.get('attchmntFile', '')}{flag}")

cls = resolved_fr.get("classification") or {}
print("\nChosen Financial Result:")
print(f"  date : {chosen.get('sort_date')}")
print(f"  title: {chosen.get('attchmntText')}")
print(f"  pdf  : {chosen_source_url}")
print(f"  pdf classification: is_fr={cls.get('is_financial_report')} "
      f"conf={cls.get('confidence')} kind={cls.get('document_kind')}")
if resolved_fr.get("recovery_needed"):
    print(f"  mislink recovery: rejected {resolved_fr.get('rejected_url', '')}")
print(f"  event_id={event_id[:12]}...")

# %% [markdown]
# ## STEP 4 / 7  -  VALUES

# %%
# =============================================================================
# STEP 4 / 7  -  VALUES
# Download the chosen Financial Result PDF, store the document, parse to markdown,
# detect the reporting period, extract facts from the target quarter column in
# markdown tables (then LLM for gaps), and persist into `extracted_values`.
# =============================================================================
import json
import re
import sys
from datetime import date, datetime, timedelta

# ---- 4a. Load OPENAI_API_KEY from v3/.env -----------------------------------
def _load_env_value(key: str) -> str:
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


OPENAI_API_KEY = _load_env_value("OPENAI_API_KEY")
OPENAI_MODEL = _load_env_value("OPENAI_MODEL") or "gpt-4.1-mini"
OPENAI_PARSE_MODEL = _load_env_value("OPENAI_PARSE_MODEL") or OPENAI_MODEL
if not OPENAI_API_KEY:
    raise RuntimeError(f"OPENAI_API_KEY not found in {ENV_PATH}")

PARSED_DIR = (REPO_ROOT / "v3" / "data" / "parsed").resolve()
PARSED_DIR.mkdir(parents=True, exist_ok=True)

# ---- 4b. Use resolved PDF from Step 3 (already downloaded + verified) ----------
pdf_url = resolved_fr["url"]
pdf_bytes = resolved_fr["pdf_bytes"]
document_id = hashlib.sha256(pdf_bytes).hexdigest()
storage_path = DOCUMENTS_DIR / f"{document_id}.pdf"
if not storage_path.exists():
    storage_path.write_bytes(pdf_bytes)

with db_connect() as conn:
    conn.execute(
        """
        INSERT OR IGNORE INTO documents (
            id, company_id, source_url, storage_path, sha256, title,
            document_kind, file_size, status
        ) VALUES (?, ?, ?, ?, ?, ?, 'FINANCIAL_RESULT', ?, 'ingested')
        """,
        (document_id, company_id, pdf_url, str(storage_path), document_id,
         chosen.get("attchmntText"), len(pdf_bytes)),
    )
    conn.execute(
        "UPDATE events SET document_id = ? WHERE id = ?", (document_id, event_id)
    )
    conn.commit()

# ---- 4c. Parse PDF → markdown (LLM vision, cached under v3/data/parsed) ------
V2_ROOT = (REPO_ROOT / "v2").resolve()
if str(V2_ROOT) not in sys.path:
    sys.path.insert(0, str(V2_ROOT))

import importlib

import pdf_parse
import quarter_column
from periods import (
    detect_reporting_period,
    fy_start_year_from_date,
    quarter_end_date,
    quarter_from_date,
    reporting_period_from_date,
)

# Pick up edits to v2 modules without restarting the kernel.
importlib.reload(pdf_parse)
importlib.reload(quarter_column)

from openai import OpenAI
from pdf_parse import parse_pdf_to_markdown
from quarter_column import extract_facts_from_quarter_column

client = OpenAI(api_key=OPENAI_API_KEY)
print("Parsing PDF to markdown (uses cache when available)...")
pdf_markdown = parse_pdf_to_markdown(
    storage_path,
    parsed_dir=PARSED_DIR,
    client=client,
    model=OPENAI_PARSE_MODEL,
)
print(f"Markdown length: {len(pdf_markdown):,} chars")

# ---- 4d. Detect reporting period ----------------------------------------------
reporting_period = detect_reporting_period(
    pdf_markdown, title=chosen.get("attchmntText") or ""
)
if reporting_period is None:
    ann = datetime.strptime(chosen["sort_date"], "%Y-%m-%d %H:%M:%S").date()
    fy = fy_start_year_from_date(ann)
    q = quarter_from_date(ann)
    reporting_period = reporting_period_from_date(
        quarter_end_date(q, fy), "announcement_fallback"
    )

period_date = date.fromisoformat(reporting_period.quarter_end)
PERIOD_QUARTER = reporting_period.quarter
PERIOD_FY_START = reporting_period.fy_start_year
PERIOD_END = reporting_period.quarter_end
PERIOD_LABEL = reporting_period.label
print(f"Reporting period: {PERIOD_LABEL}  (quarter_end={PERIOD_END})")

# ---- 4e. Fact catalog + markdown-table quarter column + LLM gap-fill ---------
facts_catalog = json.loads((CATALOG_DIR / "facts.json").read_text(encoding="utf-8"))

storage_to_fact: dict[str, str] = {}
fact_lines: list[str] = []
for key, spec in facts_catalog.items():
    storage_to_fact[key] = key
    for alias in spec.get("aliases") or []:
        storage_to_fact[str(alias)] = key
    aliases = ", ".join(spec.get("aliases") or [])
    alias_note = f" (aliases: {aliases})" if aliases else ""
    fact_lines.append(f"- {key}: {spec.get('name')} [{spec.get('unit')}]{alias_note}")
fact_catalog_text = "\n".join(fact_lines)


def _chunk(text: str, max_chars: int = 12000) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            brk = text.rfind("\n\n", start, end)
            if brk > start:
                end = brk
        chunks.append(text[start:end])
        start = end
    return chunks


def extract_facts_from_chunk(chunk: str) -> list[dict]:
    prompt = f"""Extract financial facts from this Indian corporate filing markdown.

Reporting period context: {PERIOD_LABEL}

Allowed fact_key values (use canonical keys from catalog):
{fact_catalog_text}

Rules:
- Extract ONLY values explicitly present in the markdown for the current quarter column
- Prefer consolidated over standalone when both appear
- basis must be "consolidated" or "standalone"
- numeric_value must be a number (strip commas)
- unit should match catalog (crore, Rs, etc.)
- evidence: short verbatim snippet containing the number
- confidence: 0.0 to 1.0

Return JSON object: {{"facts": [{{"fact_key": "...", "numeric_value": 0.0, "unit": "...", "basis": "consolidated", "evidence": "...", "confidence": 0.9}}]}}
If no facts found, return {{"facts": []}}.

Markdown:
{chunk}
"""
    response = client.responses.create(
        model=OPENAI_MODEL,
        input=[{"role": "user", "content": prompt}],
        text={"format": {"type": "json_object"}},
        temperature=0,
    )
    payload = json.loads((response.output_text or "{}").strip())
    facts = payload.get("facts") or []
    return [f for f in facts if isinstance(f, dict)]


deterministic_facts = extract_facts_from_quarter_column(
    pdf_markdown,
    target=reporting_period,
    fact_keys=set(facts_catalog.keys()),
    facts_catalog=facts_catalog,
)
det_by_key = {row["fact_key"]: row for row in deterministic_facts}
print(f"Deterministic (markdown tables): {len(deterministic_facts)} fact(s)")

raw_facts: list[dict] = list(deterministic_facts)
missing_keys = set(facts_catalog.keys()) - set(det_by_key)
for chunk in _chunk(pdf_markdown):
    for entry in extract_facts_from_chunk(chunk):
        fk = entry.get("fact_key")
        canonical = storage_to_fact.get(str(fk), str(fk)) if fk else None
        if canonical and canonical in det_by_key:
            continue
        if canonical and canonical not in missing_keys:
            continue
        raw_facts.append(entry)

# ---- 4f. Validate, canonicalize, and keep preferred basis (consolidated) -----
def _canon_unit(unit):
    if not unit:
        return None
    u = str(unit).strip().lower()
    return {"crores": "crore", "cr": "crore", "rs.": "Rs", "rs": "Rs"}.get(u, unit)


cleaned: dict[tuple, dict] = {}  # (fact_key, basis) -> best row
for entry in raw_facts:
    fk = entry.get("fact_key")
    if not fk:
        continue
    canonical = storage_to_fact.get(str(fk), str(fk))
    if canonical not in facts_catalog:
        continue
    try:
        numeric = float(str(entry.get("numeric_value", "")).replace(",", ""))
    except (TypeError, ValueError):
        continue
    basis = (entry.get("basis") or "consolidated").strip().lower()
    conf = float(entry.get("confidence") or 0.7)
    row = {
        "fact_key": canonical,
        "numeric_value": numeric,
        "unit": _canon_unit(entry.get("unit")) or facts_catalog[canonical].get("unit"),
        "basis": basis,
        "evidence": entry.get("evidence") or "",
        "confidence": conf,
    }
    k = (canonical, basis)
    if k not in cleaned or conf > cleaned[k]["confidence"]:
        cleaned[k] = row

# Prefer consolidated; fall back to standalone per fact_key.
preferred: dict[str, dict] = {}
for (fk, basis), row in cleaned.items():
    cur = preferred.get(fk)
    if cur is None or (basis == "consolidated" and cur["basis"] != "consolidated"):
        preferred[fk] = row

accepted_rows = list(preferred.values())
if not accepted_rows:
    raise RuntimeError("No facts passed validation after extraction")

# ---- 4g. Persist into extracted_values ---------------------------------------
def value_id(value_code: str, period_end: str, basis: str) -> str:
    return hashlib.sha256(
        f"{company_id}:{value_code}:{period_end}:{basis}".encode()
    ).hexdigest()


with db_connect() as conn:
    for row in accepted_rows:
        vid = value_id(row["fact_key"], PERIOD_END, row["basis"])
        conn.execute(
            """
            INSERT INTO extracted_values (
                id, company_id, event_id, value_code, value_numeric, unit,
                period_type, period_start, period_end, basis, source_text, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, 'quarter', NULL, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                event_id = excluded.event_id,
                value_numeric = excluded.value_numeric,
                unit = excluded.unit,
                source_text = excluded.source_text,
                confidence = excluded.confidence
            """,
            (vid, company_id, event_id, row["fact_key"], row["numeric_value"],
             row["unit"], PERIOD_END, row["basis"], row["evidence"], row["confidence"]),
        )
    conn.execute(
        "UPDATE events SET status = 'processed', fiscal_year = ?, fiscal_quarter = ? WHERE id = ?",
        (PERIOD_FY_START, PERIOD_QUARTER, event_id),
    )
    conn.execute(
        "UPDATE documents SET status = 'processed' WHERE id = ?", (document_id,)
    )
    conn.commit()

print(f"\nExtracted {len(accepted_rows)} fact(s) for {PERIOD_LABEL}:")
for row in sorted(accepted_rows, key=lambda r: r["fact_key"]):
    print(f"  {row['fact_key']:<26} {row['numeric_value']:>14,.2f} {row['unit'] or '':<8} "
          f"[{row['basis']}]")

# %% [markdown]
# ## STEP 5 / 7  -  METRICS

# %%
# =============================================================================
# STEP 5 / 7  -  METRICS
# Seed the metric catalog, load CURRENT / prior-year / prior-quarter facts,
# evaluate the catalog formulas, and persist results into `metric_values`.
# (YoY / QoQ metrics only compute once those prior quarters exist in the DB.)
# =============================================================================
metrics_catalog = json.loads((CATALOG_DIR / "metrics.json").read_text(encoding="utf-8"))

# ---- 5a. Seed the `metrics` catalog table (mirrors v3/seed_catalog.py) --------
with db_connect() as conn:
    for code, spec in metrics_catalog.items():
        mid = hashlib.sha256(code.encode()).hexdigest()
        formula_payload = json.dumps({
            "formula": spec.get("formula"),
            "inputs": spec.get("inputs") or [],
            "category": spec.get("category"),
        })
        conn.execute(
            """
            INSERT INTO metrics (id, metric_code, name, formula, unit, description)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(metric_code) DO UPDATE SET
                name = excluded.name, formula = excluded.formula,
                unit = excluded.unit, description = excluded.description
            """,
            (mid, code, spec.get("name", code), formula_payload,
             spec.get("unit"), spec.get("category")),
        )
    conn.commit()

# ---- 5b. Load fact pools for CURRENT, prior-year, prior-quarter --------------
def prior_year_end() -> str:
    return quarter_end_date(PERIOD_QUARTER, PERIOD_FY_START - 1).isoformat()


def prior_quarter_end() -> str:
    if PERIOD_QUARTER == 1:
        q, fy = 4, PERIOD_FY_START - 1
    else:
        q, fy = PERIOD_QUARTER - 1, PERIOD_FY_START
    return quarter_end_date(q, fy).isoformat()


def load_facts(period_end: str) -> dict[str, dict]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT value_code, value_numeric, unit FROM extracted_values
            WHERE company_id = ? AND period_end = ?
            ORDER BY CASE basis WHEN 'consolidated' THEN 0 ELSE 1 END
            """,
            (company_id, period_end),
        ).fetchall()
    pool: dict[str, dict] = {}
    for r in rows:
        if r["value_numeric"] is None:
            continue
        pool.setdefault(r["value_code"],
                        {"value": float(r["value_numeric"]), "unit": r["unit"]})
    return pool


facts_current = load_facts(PERIOD_END)
facts_py = load_facts(prior_year_end())
facts_pq = load_facts(prior_quarter_end())
SCOPE_POOLS = {"CURRENT": facts_current, "PY": facts_py, "PQ": facts_pq}

# ---- 5c. Unit -> crore-equivalent scaling for cross-scope comparison ---------
_UNIT_SCALE = {
    "crore": 1.0, "crores": 1.0, "cr": 1.0, "lakh": 0.01, "lakhs": 0.01,
    "lac": 0.01, "lacs": 0.01, "million": 0.1, "mn": 0.1, "billion": 100.0,
    "bn": 100.0, "thousand": 1e-5,
}
_PASS_THROUGH = {"%", "percent", "pct", "bps", "rs", "rs.", "inr", "x", "times", "days"}


def crore_scale(unit):
    if not unit:
        return None
    u = str(unit).strip().lower()
    if u in _PASS_THROUGH:
        return None
    return _UNIT_SCALE.get(u)


def resolve_inputs(inputs: list[dict]):
    scopes = {i["scope"].upper() for i in inputs}
    use_comparable = len(scopes) > 1
    resolved: dict[str, float] = {}
    for inp in inputs:
        pool = SCOPE_POOLS.get(inp["scope"].upper(), {})
        detail = pool.get(inp["fact_key"])
        if detail is None:
            return None
        val = detail["value"]
        if use_comparable:
            scale = crore_scale(detail["unit"])
            if scale is not None:
                val = val * scale
        resolved[inp["var"]] = val
    return resolved


def safe_eval(formula: str, variables: dict[str, float]):
    namespace = {"__builtins__": {}, "min": min, "max": max, "abs": abs, **variables}
    try:
        result = eval(formula, namespace)  # trusted catalog formulas only
    except ZeroDivisionError:
        return None
    return float(result) if isinstance(result, (int, float)) else None


# ---- 5d. Compute and persist metric values -----------------------------------
computed_metrics: list[dict] = []
for code, spec in metrics_catalog.items():
    variables = resolve_inputs(spec.get("inputs") or [])
    if variables is None:
        continue
    value = safe_eval(spec["formula"], variables)
    if value is None:
        continue
    computed_metrics.append({
        "metric_key": code,
        "name": spec.get("name", code),
        "value": round(value, 2),
        "unit": spec.get("unit"),
        "category": spec.get("category"),
        "formula": spec["formula"],
        "inputs": sorted({i["fact_key"] for i in spec.get("inputs") or []}),
    })

with db_connect() as conn:
    conn.execute(
        "DELETE FROM metric_values WHERE company_id = ? AND event_id = ?",
        (company_id, event_id),
    )
    for m in computed_metrics:
        mid_row = conn.execute(
            "SELECT id FROM metrics WHERE metric_code = ?", (m["metric_key"],)
        ).fetchone()
        if not mid_row:
            continue
        mvid = hashlib.sha256(
            f"{company_id}:{event_id}:{m['metric_key']}".encode()
        ).hexdigest()
        conn.execute(
            """
            INSERT INTO metric_values (
                id, company_id, event_id, metric_id, metric_value,
                period_start, period_end, calculation_data
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (mvid, company_id, event_id, mid_row["id"], m["value"], PERIOD_END,
             json.dumps({"unit": m["unit"], "formula": m["formula"], "inputs": m["inputs"]})),
        )
    conn.commit()

print(f"Computed {len(computed_metrics)} metric(s) for {PERIOD_LABEL}")
if not facts_py:
    print("  (no prior-year facts in DB -> YoY metrics skipped)")
if not facts_pq:
    print("  (no prior-quarter facts in DB -> QoQ metrics skipped)")
print()
for m in computed_metrics:
    print(f"  {m['name']:<32} {m['value']:>12,.2f} {m['unit'] or '':<5}  [{m['category']}]")

# %% [markdown]
# ## STEP 6 / 7  -  SIGNALS

# %%
# =============================================================================
# STEP 6 / 7  -  SIGNALS
# Evaluate the signal-rule catalog against the computed metrics and persist
# every fired signal into the `signals` table.
# =============================================================================
signals_catalog = json.loads((CATALOG_DIR / "signals.json").read_text(encoding="utf-8"))

metrics_by_key = {m["metric_key"]: m for m in computed_metrics}

_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def eval_leaf(rule: dict) -> bool:
    m = metrics_by_key.get(rule["metric_key"])
    if m is None:
        return False
    return _OPS[rule["op"]](m["value"], rule["value"])


def eval_rule(rule: dict) -> bool:
    if "all" in rule:
        return all(eval_rule(child) for child in rule["all"])
    if "any" in rule:
        return any(eval_rule(child) for child in rule["any"])
    if "metric_key" in rule:
        return eval_leaf(rule)
    raise ValueError(f"Malformed rule: {rule}")


def rule_metric_keys(rule: dict) -> list[str]:
    if "metric_key" in rule:
        return [rule["metric_key"]]
    keys: list[str] = []
    for k in ("all", "any"):
        for child in rule.get(k, []):
            keys.extend(rule_metric_keys(child))
    return keys


def format_rule(rule: dict) -> str:
    if "metric_key" in rule:
        return f"{rule['metric_key']} {rule['op']} {rule['value']}"
    if "all" in rule:
        return " AND ".join(f"({format_rule(c)})" for c in rule["all"])
    if "any" in rule:
        return " OR ".join(f"({format_rule(c)})" for c in rule["any"])
    return ""


fired_signals: list[dict] = []
for code, spec in signals_catalog.items():
    rule = spec.get("rule")
    if not rule:
        continue
    # A rule can only fire if every metric it references was computed.
    keys = rule_metric_keys(rule)
    if not all(k in metrics_by_key for k in keys):
        continue
    if not eval_rule(rule):
        continue
    trigger = {k: metrics_by_key[k]["value"] for k in keys if k in metrics_by_key}
    fired_signals.append({
        "signal_key": code,
        "title": spec.get("name", code),
        "description": spec.get("description", ""),
        "direction": spec.get("direction"),
        "severity": spec.get("severity"),
        "category": spec.get("category"),
        "metric_keys": keys,
        "trigger_values": trigger,
        "rule_text": format_rule(rule),
    })

# ---- Persist fired signals ---------------------------------------------------
with db_connect() as conn:
    conn.execute(
        "DELETE FROM signals WHERE company_id = ? AND event_id = ?",
        (company_id, event_id),
    )
    for s in fired_signals:
        sid = hashlib.sha256(
            f"{company_id}:{event_id}:{s['signal_key']}".encode()
        ).hexdigest()
        conn.execute(
            """
            INSERT INTO signals (
                id, company_id, event_id, signal_type, title, description,
                direction, severity, evidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sid, company_id, event_id, s["signal_key"], s["title"], s["description"],
             s["direction"], s["severity"],
             json.dumps({"metric_keys": s["metric_keys"],
                         "trigger_values": s["trigger_values"],
                         "rule_text": s["rule_text"],
                         "category": s["category"]})),
        )
    conn.commit()

print(f"Evaluated {len(signals_catalog)} signal rules -> {len(fired_signals)} fired\n")
for s in fired_signals:
    print(f"  [{s['severity']}/{s['direction']}] {s['title']}")
    print(f"        rule: {s['rule_text']}  ->  {s['trigger_values']}")

# %% [markdown]
# ## STEP 7 / 7  -  ALERTS

# %%
# =============================================================================
# STEP 7 / 7  -  ALERTS
# Read the fired signals back from the DB and present them as alerts,
# then print a final per-event DB summary.
# =============================================================================
with db_connect() as conn:
    alert_rows = conn.execute(
        """
        SELECT signal_type, title, description, direction, severity, evidence
        FROM signals WHERE company_id = ? AND event_id = ?
        """,
        (company_id, event_id),
    ).fetchall()

    counts = {
        "extracted_values": conn.execute(
            "SELECT COUNT(*) c FROM extracted_values WHERE event_id = ?", (event_id,)
        ).fetchone()["c"],
        "metric_values": conn.execute(
            "SELECT COUNT(*) c FROM metric_values WHERE event_id = ?", (event_id,)
        ).fetchone()["c"],
        "signals": conn.execute(
            "SELECT COUNT(*) c FROM signals WHERE event_id = ?", (event_id,)
        ).fetchone()["c"],
    }

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

print("=" * 70)
print(f"ALERTS  -  {SYMBOL}  -  {EVENT_TYPE}  -  {PERIOD_LABEL}")
print("=" * 70)

if not alert_rows:
    print("\nNo signals triggered for this filing.")
else:
    ordered = sorted(alert_rows, key=lambda r: _SEVERITY_ORDER.get(r["severity"], 9))
    for r in ordered:
        evidence = json.loads(r["evidence"]) if r["evidence"] else {}
        triggers = evidence.get("trigger_values", {})
        print(f"\n  [{r['severity']}] {r['title']}  ({r['direction']})")
        print(f"      {r['description']}")
        if triggers:
            trig = ", ".join(f"{k}={v}" for k, v in triggers.items())
            print(f"      triggered by: {trig}")

print("\n" + "-" * 70)
print(f"DB summary for event {event_id[:12]}...:")
print(f"  extracted_values : {counts['extracted_values']}")
print(f"  metric_values    : {counts['metric_values']}")
print(f"  signals          : {counts['signals']}")
print(f"\nAll seven steps complete. Data persisted to {DB_PATH}")


