"""Ingest job queue endpoints.

POST  /ingest/{distro}/{release}   — enqueue a job (maintainer+)
GET   /ingest/jobs                 — list jobs (maintainer+)
GET   /ingest/jobs/{job_id}        — get single job (public)
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_pool
from .auth import require_role

router = APIRouter(tags=["ingest"])

_COOLDOWN_HOURS = int(os.getenv("INGEST_COOLDOWN_HOURS", "6"))


@router.post("/ingest/{distro}/{release}", status_code=202)
async def enqueue_ingest(
    distro: str,
    release: str,
    user: Annotated[dict, Depends(require_role("maintainer"))],
) -> dict:
    """Enqueue an ingest job for *distro*/*release*.

    Requires ``maintainer`` or ``admin`` role.
    Returns 409 if a job is already pending/running.
    Returns 429 if the last successful ingest finished within the cooldown window.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        # Check for an active job
        active = await conn.fetchrow(
            "SELECT id, status FROM ingest_jobs "
            "WHERE distro = $1 AND release = $2 AND status IN ('pending', 'running')",
            distro,
            release,
        )
        if active:
            raise HTTPException(
                409,
                f"An ingest job for {distro}/{release} is already {active['status']} "
                f"(job #{active['id']}).",
            )

        # Check cooldown
        last_done = await conn.fetchrow(
            "SELECT id, finished_at FROM ingest_jobs "
            "WHERE distro = $1 AND release = $2 AND status = 'done' "
            "ORDER BY finished_at DESC LIMIT 1",
            distro,
            release,
        )
        if last_done and last_done["finished_at"]:
            from datetime import datetime, timezone
            elapsed = datetime.now(timezone.utc) - last_done["finished_at"]
            if elapsed.total_seconds() < _COOLDOWN_HOURS * 3600:
                remaining_mins = int(
                    (_COOLDOWN_HOURS * 3600 - elapsed.total_seconds()) / 60
                )
                raise HTTPException(
                    429,
                    f"Last ingest for {distro}/{release} finished recently. "
                    f"Please wait ~{remaining_mins} more minute(s).",
                )

        # Resolve optional source_id from distro_sources
        source = await conn.fetchrow(
            "SELECT id FROM distro_sources WHERE distro = $1 AND release = $2 AND enabled",
            distro,
            release,
        )

        row = await conn.fetchrow(
            """
            INSERT INTO ingest_jobs (distro, release, source_id, triggered_by)
            VALUES ($1, $2, $3, $4)
            RETURNING id, distro, release, status, created_at
            """,
            distro,
            release,
            source["id"] if source else None,
            user["id"],
        )

    result = dict(row)
    result["created_at"] = result["created_at"].isoformat()
    return result


@router.get("/ingest/jobs")
async def list_jobs(
    user: Annotated[dict, Depends(require_role("maintainer"))],
    distro: str | None = None,
    release: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """List recent ingest jobs (maintainer+)."""
    pool = get_pool()
    filters = ["TRUE"]
    params: list = []
    idx = 1

    if distro:
        filters.append(f"j.distro = ${idx}")
        params.append(distro)
        idx += 1
    if release:
        filters.append(f"j.release = ${idx}")
        params.append(release)
        idx += 1
    if status:
        filters.append(f"j.status = ${idx}")
        params.append(status)
        idx += 1

    params.append(limit)
    where = " AND ".join(filters)

    sql = f"""
        SELECT j.id, j.distro, j.release, j.status,
               j.packages_upserted, j.error_message,
               j.started_at, j.finished_at, j.created_at,
               u.display_name AS triggered_by_name
        FROM ingest_jobs j
        LEFT JOIN users u ON u.id = j.triggered_by
        WHERE {where}
        ORDER BY j.created_at DESC
        LIMIT ${idx}
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)

    def _fmt(row: dict) -> dict:
        for k in ("started_at", "finished_at", "created_at"):
            if row.get(k):
                row[k] = row[k].isoformat()
        return row

    return {"jobs": [_fmt(dict(r)) for r in rows]}


@router.get("/ingest/jobs/{job_id}")
async def get_job(job_id: int) -> dict:
    """Get a single ingest job by id (public)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT j.id, j.distro, j.release, j.status,
                   j.packages_upserted, j.error_message,
                   j.started_at, j.finished_at, j.created_at,
                   u.display_name AS triggered_by_name
            FROM ingest_jobs j
            LEFT JOIN users u ON u.id = j.triggered_by
            WHERE j.id = $1
            """,
            job_id,
        )
    if row is None:
        raise HTTPException(404, f"job #{job_id} not found")
    result = dict(row)
    for k in ("started_at", "finished_at", "created_at"):
        if result.get(k):
            result[k] = result[k].isoformat()
    return result
