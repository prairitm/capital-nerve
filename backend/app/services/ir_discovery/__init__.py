"""IR discovery + bulk ingestion.

Public entry points for the `python -m app.scripts.bulk_ingest` CLI:

- `expand_range` — turns CLI date / quarter / last-N inputs into a list of
  `PeriodSpec` objects.
- `find_period_assets` — async OpenAI-Agents SDK call that locates the
  result PDF / concall transcript / presentation / (optional) annual report
  for one (Company, PeriodSpec) pair.
- `ingest_one` — downloads each asset, persists `CompanyEvent` +
  `SourceDocument` + `ExtractionJob`, then runs `run_pipeline_for_document`
  inline so the DB end-state matches `POST /ingest/upload`.

Nothing in this package may be imported by routers — the CLI is the only
caller.
"""
from app.services.ir_discovery.agent import find_period_assets
from app.services.ir_discovery.ingest import IngestOutcome, ingest_one
from app.services.ir_discovery.periods import expand_range
from app.services.ir_discovery.schemas import (
    AssetMatch,
    CompanyRef,
    PeriodAssetSet,
    PeriodSpec,
)

__all__ = [
    "AssetMatch",
    "CompanyRef",
    "IngestOutcome",
    "PeriodAssetSet",
    "PeriodSpec",
    "expand_range",
    "find_period_assets",
    "ingest_one",
]
