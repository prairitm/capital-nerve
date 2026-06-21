"""historical-anomaly flag on calculated_metrics

Phase 1D of the metric-governance roadmap. Static bounds (``validation_min``
/ ``validation_max``) catch impossible values like 1927 % segment margin
but pass values that are "merely improbable" — e.g. RELIANCE Q2 FY25 PAT
margin of 60.8 % because the extractor matched a segment revenue figure
("Jio Platforms Operating Revenue") to consolidated ``revenue_from_operations``.

This migration adds:

- ``calculated_metrics.anomaly_flag`` — set by
  ``services/pipeline/metric_anomaly.check_anomaly`` when the value is too
  far from the company's own historical distribution for the same metric.
- ``calculated_metrics.anomaly_reason`` — human-readable explanation
  (median, deviation) for the Review Queue and the analyst-trust badge.

Revision ID: 0008_metric_anomaly
Revises: 0007_metric_kind
Create Date: 2026-05-25 22:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_metric_anomaly"
down_revision: Union[str, None] = "0007_metric_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "calculated_metrics",
        sa.Column(
            "anomaly_flag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "calculated_metrics",
        sa.Column("anomaly_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("calculated_metrics", "anomaly_reason")
    op.drop_column("calculated_metrics", "anomaly_flag")
