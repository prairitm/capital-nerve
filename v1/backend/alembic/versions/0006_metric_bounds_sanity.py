"""metric output bounds + comparator-integrity column

Adds the columns required by Phase 1A of the analyst-trust overhaul:

- ``metric_definitions.validation_min`` / ``validation_max`` — plausible
  range for each metric output. The metrics stage quarantines values
  outside these bounds so a 1927 %% segment margin never reaches signals.
- ``calculated_metrics.is_quarantined`` / ``quarantine_reason`` — set on
  rows that breach the bounds. Quarantined rows are persisted for the
  Review Queue but never feed the signals / cards stages.
- ``extracted_values.column_label`` / ``financial_statement_facts.column_label``
  — period-column label the value was pulled from ("Q3 FY24-25", "9M",
  "YTD"). The ``InputResolver`` comparator-integrity check skips PQ/PY
  lookups against YTD/9M/H1 columns so QoQ never divides by a year-to-date
  number.

Revision ID: 0006_metric_bounds_sanity
Revises: 0005_extraction_cache
Create Date: 2026-05-25 21:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_metric_bounds_sanity"
down_revision: Union[str, None] = "0005_extraction_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "metric_definitions",
        sa.Column("validation_min", sa.Numeric(24, 6), nullable=True),
    )
    op.add_column(
        "metric_definitions",
        sa.Column("validation_max", sa.Numeric(24, 6), nullable=True),
    )
    op.add_column(
        "calculated_metrics",
        sa.Column(
            "is_quarantined",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "calculated_metrics",
        sa.Column("quarantine_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "extracted_values",
        sa.Column("column_label", sa.String(), nullable=True),
    )
    op.add_column(
        "financial_statement_facts",
        sa.Column("column_label", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("financial_statement_facts", "column_label")
    op.drop_column("extracted_values", "column_label")
    op.drop_column("calculated_metrics", "quarantine_reason")
    op.drop_column("calculated_metrics", "is_quarantined")
    op.drop_column("metric_definitions", "validation_max")
    op.drop_column("metric_definitions", "validation_min")
