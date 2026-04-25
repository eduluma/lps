"""distro onboarding: user roles, distro_sources, distro_requests, ingest_jobs

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-23
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SQL_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"


def upgrade() -> None:
    op.execute((SQL_DIR / "0004_ingest_jobs.up.sql").read_text())


def downgrade() -> None:
    op.execute((SQL_DIR / "0004_ingest_jobs.down.sql").read_text())
