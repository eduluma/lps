"""crowd-sourced suggestions tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-22
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"


def upgrade() -> None:
    op.execute((SQL_DIR / "0002_suggestions.up.sql").read_text())


def downgrade() -> None:
    op.execute((SQL_DIR / "0002_suggestions.down.sql").read_text())
