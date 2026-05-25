"""Tier-1 (BSE / NSE) IR discovery.

`discover_period_assets` is the default BSE-first + NSE-fallback entry
point used by the bulk ingest CLI. `discover_period_assets_via_scraper`
is the alternate NSE-only, no-date-range scraper triggered by the
``--nse-scraper`` flag.
"""
from app.services.ir_discovery.exchange.discover import (
    DiscoveryResult,
    discover_period_assets,
)
from app.services.ir_discovery.exchange.nse_scraper import (
    discover_period_assets_via_scraper,
)

__all__ = [
    "DiscoveryResult",
    "discover_period_assets",
    "discover_period_assets_via_scraper",
]
