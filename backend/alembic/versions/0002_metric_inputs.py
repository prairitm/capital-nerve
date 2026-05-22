"""metric definition inputs + dependencies

Adds the columns the Section 18 config-driven engine reads:

- ``metric_definitions.inputs_json``   — list of input declarations consumed by
  ``services/pipeline/inputs.py::InputResolver``.
- ``metric_definitions.dependencies_json`` — list of upstream metric codes used
  to topo-sort metric-of-metric formulas (e.g. ``fcf`` depends on ``cfo`` and
  ``capex_ppe``).

Revision ID: 0002_metric_inputs
Revises: 0001_initial
Create Date: 2026-05-21 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002_metric_inputs"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "metric_definitions",
        sa.Column("inputs_json", JSONB, nullable=False, server_default="[]"),
    )
    op.add_column(
        "metric_definitions",
        sa.Column("dependencies_json", JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("metric_definitions", "dependencies_json")
    op.drop_column("metric_definitions", "inputs_json")
