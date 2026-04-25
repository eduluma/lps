"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-21
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"


def upgrade() -> None:
    op.execute((SQL_DIR / "0001_initial.up.sql").read_text())


def downgrade() -> None:
    op.execute((SQL_DIR / "0001_initial.down.sql").read_text())
