"""extraction_jobs cache + determinism bookkeeping

Adds the columns needed to make extraction deterministic and idempotent:

- ``request_hash`` — sha256 of (file_hash, prompt_version, model, seed,
  parser_version). The extraction stage looks up the most recent COMPLETED
  job with the same hash and replays its cached payload instead of calling
  the LLM again.
- ``raw_response`` — canonical JSON returned by the provider (Anthropic
  tool-call payload or OpenAI strict json_schema response). Replay parses this.
- ``llm_temperature`` / ``llm_seed`` — sampling settings captured at call time
  so the admin Review Queue can show *why* two runs produced different output.
- ``provider_used`` — anthropic / openai / mock; surfaces the upstream choice
  even when the configured provider was unavailable.
- ``validator_report`` — JSONB collecting per-validator outcomes
  (source-text check, unit canonicalisation, totals math) so the review UI
  can explain a low confidence score.

Revision ID: 0005_extraction_cache
Revises: 0004_document_search
Create Date: 2026-05-25 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_extraction_cache"
down_revision: Union[str, None] = "0004_document_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "extraction_jobs",
        sa.Column("request_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "extraction_jobs",
        sa.Column("raw_response", sa.Text(), nullable=True),
    )
    op.add_column(
        "extraction_jobs",
        sa.Column("llm_temperature", sa.Numeric(3, 2), nullable=True),
    )
    op.add_column(
        "extraction_jobs",
        sa.Column("llm_seed", sa.Integer(), nullable=True),
    )
    op.add_column(
        "extraction_jobs",
        sa.Column("provider_used", sa.String(), nullable=True),
    )
    op.add_column(
        "extraction_jobs",
        sa.Column(
            "validator_report",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_extraction_jobs_request_hash",
        "extraction_jobs",
        ["request_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_jobs_request_hash", table_name="extraction_jobs")
    op.drop_column("extraction_jobs", "validator_report")
    op.drop_column("extraction_jobs", "provider_used")
    op.drop_column("extraction_jobs", "llm_seed")
    op.drop_column("extraction_jobs", "llm_temperature")
    op.drop_column("extraction_jobs", "raw_response")
    op.drop_column("extraction_jobs", "request_hash")
