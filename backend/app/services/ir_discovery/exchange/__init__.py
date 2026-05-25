"""Tier-1 (BSE / NSE) IR discovery.

`discover_period_assets` is the public entry point used by the bulk
ingest CLI. Everything else in this package is an implementation
detail of that one function.
"""
from app.services.ir_discovery.exchange.discover import (
    DiscoveryResult,
    discover_period_assets,
)

__all__ = ["DiscoveryResult", "discover_period_assets"]
