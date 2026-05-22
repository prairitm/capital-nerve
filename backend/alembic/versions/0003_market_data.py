"""market data points

Adds the daily OHLCV / delivery snapshot table that backs the valuation and
market-reaction cards. The engine reads market data through
``financial_statement_facts`` rows keyed by `share_price_close`, `volume`,
etc.; this table holds the raw daily series so the projection isn't lossy.

Revision ID: 0003_market_data
Revises: 0002_metric_inputs
Create Date: 2026-05-21 00:10:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_market_data"
down_revision: Union[str, None] = "0002_metric_inputs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_data_points",
        sa.Column("market_data_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.company_id"), nullable=False),
        sa.Column("trade_date", sa.Date, nullable=False),
        sa.Column("open_price", sa.Numeric(24, 6)),
        sa.Column("high_price", sa.Numeric(24, 6)),
        sa.Column("low_price", sa.Numeric(24, 6)),
        sa.Column("close_price", sa.Numeric(24, 6)),
        sa.Column("volume", sa.Numeric(24, 6)),
        sa.Column("delivery_qty", sa.Numeric(24, 6)),
        sa.Column("delivery_pct", sa.Numeric(12, 4)),
        sa.Column("avg_volume_20d", sa.Numeric(24, 6)),
        sa.Column("market_cap", sa.Numeric(24, 6)),
        sa.Column("fifty_two_week_high", sa.Numeric(24, 6)),
        sa.Column("fifty_two_week_low", sa.Numeric(24, 6)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "trade_date", name="uq_market_data_points"),
    )


def downgrade() -> None:
    op.drop_table("market_data_points")
