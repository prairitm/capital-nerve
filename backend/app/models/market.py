"""Market-data tables.

Lives in its own file because market data is a different domain from
financial facts: it's pulled from price feeds (NSE bhavcopy / paid API /
manual CSV upload), not from filings, and the cardinality is one row per
(company, date) versus one row per (company, period, line item).

The metric engine reads market data through `FinancialStatementFact` rows
keyed by `share_price_close`, `volume`, `avg_volume_20d`, `market_cap`, etc.
The router that ingests `MarketDataPoint` rows is responsible for projecting
the latest snapshot down into facts so the engine doesn't need a custom
pipeline stage for valuation metrics.
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketDataPoint(Base):
    """Daily OHLCV + delivery snapshot for one company.

    Two derived columns (`avg_volume_20d`, `market_cap`) are pre-computed at
    write time so the engine doesn't need a window function over this table
    every time it values a company.
    """

    __tablename__ = "market_data_points"
    __table_args__ = (
        UniqueConstraint("company_id", "trade_date", name="uq_market_data_points"),
    )

    market_data_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.company_id"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    open_price: Mapped[float | None] = mapped_column(Numeric(24, 6))
    high_price: Mapped[float | None] = mapped_column(Numeric(24, 6))
    low_price: Mapped[float | None] = mapped_column(Numeric(24, 6))
    close_price: Mapped[float | None] = mapped_column(Numeric(24, 6))
    volume: Mapped[float | None] = mapped_column(Numeric(24, 6))
    delivery_qty: Mapped[float | None] = mapped_column(Numeric(24, 6))
    delivery_pct: Mapped[float | None] = mapped_column(Numeric(12, 4))

    avg_volume_20d: Mapped[float | None] = mapped_column(Numeric(24, 6))
    market_cap: Mapped[float | None] = mapped_column(Numeric(24, 6))

    fifty_two_week_high: Mapped[float | None] = mapped_column(Numeric(24, 6))
    fifty_two_week_low: Mapped[float | None] = mapped_column(Numeric(24, 6))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
