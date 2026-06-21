"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

from app.db.base import Base
from app.models import *  # noqa: F401, F403  (register all models on Base.metadata)

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
