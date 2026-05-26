"""metric_kind ontology column + composite acceleration metric scope

Phase 1A of the metric-governance roadmap. Adds:

- ``metric_definitions.metric_kind`` — product-level ontology badge so the
  feed can distinguish a derived financial ratio (``pat_margin``) from a
  concall lexicon score (``concall_capex_intent_score``) from a metric that
  reads other metrics (the new ``revenue_yoy_growth_acceleration_pp``).

The follow-on seeder backfills the column for every existing row; this
migration leaves the existing default (``financial``) so prior data is
never NULL.

Revision ID: 0007_metric_kind
Revises: 0006_metric_bounds_sanity
Create Date: 2026-05-25 22:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_metric_kind"
down_revision: Union[str, None] = "0006_metric_bounds_sanity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "metric_definitions",
        sa.Column(
            "metric_kind",
            sa.String(),
            nullable=False,
            server_default="financial",
        ),
    )


def downgrade() -> None:
    op.drop_column("metric_definitions", "metric_kind")
