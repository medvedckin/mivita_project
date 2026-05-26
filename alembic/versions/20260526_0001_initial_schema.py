"""initial schema

Revision ID: 20260526_0001
Revises:
Create Date: 2026-05-26

Baseline migration: creates every table declared in models.* via
Base.metadata.create_all. From this point on use `alembic revision
--autogenerate -m "<msg>"` for changes.
"""
from typing import Sequence, Union

from alembic import op

from database import Base
import models  # noqa: F401  — register models on Base.metadata


revision: str = "20260526_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
