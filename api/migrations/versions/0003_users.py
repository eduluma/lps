"""registered users and API tokens

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-22
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"


def upgrade() -> None:
    op.execute((SQL_DIR / "0003_users.up.sql").read_text())


def downgrade() -> None:
    op.execute((SQL_DIR / "0003_users.down.sql").read_text())
