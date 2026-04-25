from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from ..db import get_pool
from .auth import require_role

router = APIRouter(tags=["distros"])

_URL_RE = re.compile(r"^https?://")


class DistroRequestIn(BaseModel):
    distro_name: str
    release_name: str | None = None
    format: str | None = None
    base_url: str | None = None
    description: str | None = None
    contact_info: str | None = None

    @field_validator("distro_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 80:
            raise ValueError("Distro name must be 1–80 characters.")
        return v

    @field_validator("format")
    @classmethod
    def _fmt(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in ("apt", "rpm", "apk", "aur", "other"):
            raise ValueError("format must be one of: apt, rpm, apk, aur, other.")
        return v

    @field_validator("base_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        if not v:
            return None
        v = v.strip()
        if not _URL_RE.match(v):
            raise ValueError("base_url must start with http:// or https://.")
        if len(v) > 500:
            raise ValueError("base_url must be ≤ 500 characters.")
        return v

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        return v[:1000]  # hard-truncate rather than error

    @field_validator("contact_info")
    @classmethod
    def _contact(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return v.strip()[:200]


@router.get("/distros")
async def list_distros() -> dict:
    """List all distros with their releases nested and last ingest timestamp."""
    pool = get_pool()
    async with pool.acquire() as conn:
        distro_rows = await conn.fetch("SELECT * FROM distros ORDER BY name")
        release_rows = await conn.fetch("SELECT * FROM releases ORDER BY distro_id, name")
        # Most recent successful ingest per distro — prefer ingest_jobs,
        # fall back to MAX(packages.updated_at) for CLI-driven ingests.
        ingest_rows = await conn.fetch(
            """
            WITH job_stats AS (
                SELECT DISTINCT ON (distro)
                    distro,
                    release          AS last_ingest_release,
                    finished_at      AS last_ingest_at,
                    packages_upserted AS last_ingest_count
                FROM ingest_jobs
                WHERE status = 'done' AND finished_at IS NOT NULL
                ORDER BY distro, finished_at DESC
            ),
            pkg_stats AS (
                SELECT distro, MAX(updated_at) AS last_ingest_at
                FROM packages
                GROUP BY distro
            )
            SELECT
                COALESCE(j.distro, p.distro)          AS distro,
                j.last_ingest_release,
                COALESCE(j.last_ingest_at, p.last_ingest_at) AS last_ingest_at,
                j.last_ingest_count
            FROM pkg_stats p
            LEFT JOIN job_stats j ON j.distro = p.distro
            """
        )
    releases_by_distro: dict[int, list] = {}
    for r in release_rows:
        releases_by_distro.setdefault(r["distro_id"], []).append(dict(r))
    ingest_by_distro: dict[str, dict] = {
        r["distro"]: {
            "last_ingest_at": r["last_ingest_at"].isoformat() if r["last_ingest_at"] else None,
            "last_ingest_release": r["last_ingest_release"],
            "last_ingest_count": r["last_ingest_count"],
        }
        for r in ingest_rows
    }
    distros = []
    for d in distro_rows:
        d_dict = dict(d)
        d_dict["releases"] = releases_by_distro.get(d["id"], [])
        d_dict.update(
            ingest_by_distro.get(
                d["name"],
                {
                    "last_ingest_at": None,
                    "last_ingest_release": None,
                    "last_ingest_count": None,
                },
            )
        )
        distros.append(d_dict)
    return {"distros": distros}


@router.get("/distros/{name}/releases")
async def list_distro_releases(name: str) -> dict:
    """List all releases for a specific distro."""
    pool = get_pool()
    async with pool.acquire() as conn:
        distro = await conn.fetchrow("SELECT id FROM distros WHERE name = $1", name)
        if distro is None:
            raise HTTPException(status_code=404, detail=f"distro '{name}' not found")
        rows = await conn.fetch(
            "SELECT * FROM releases WHERE distro_id = $1 ORDER BY name",
            distro["id"],
        )
    return {"distro": name, "releases": [dict(r) for r in rows]}


@router.get("/stats")
async def stats() -> dict:
    """Package counts per distro plus site-wide aggregates."""
    pool = get_pool()
    async with pool.acquire() as conn:
        pkg_rows = await conn.fetch(
            "SELECT distro, COUNT(*) AS count FROM packages GROUP BY distro ORDER BY count DESC"
        )
        suggestion_row = await conn.fetchrow(
            "SELECT COUNT(*) AS count FROM suggestions WHERE status = 'pending'"
        )
        distro_row = await conn.fetchrow("SELECT COUNT(*) AS count FROM distros")
    total = sum(r["count"] for r in pkg_rows)
    return {
        "total": total,
        "distros_count": distro_row["count"] if distro_row else 0,
        "suggestions_pending": suggestion_row["count"] if suggestion_row else 0,
        "by_distro": [{"distro": r["distro"], "count": r["count"]} for r in pkg_rows],
    }


@router.post("/distros/request", status_code=201)
async def request_distro(payload: DistroRequestIn) -> dict:
    """Submit a request to add a new distro (open to all, anon OK)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        # Prevent duplicate pending requests for the same distro/release
        dup = await conn.fetchval(
            "SELECT id FROM distro_requests "
            "WHERE lower(distro_name) = lower($1) "
            "  AND (release_name IS NULL OR lower(release_name) = lower($2)) "
            "  AND status = 'pending'",
            payload.distro_name,
            payload.release_name or "",
        )
        if dup:
            raise HTTPException(
                409,
                f"A pending request for '{payload.distro_name}' already exists. "
                "You can follow its progress.",
            )
        row = await conn.fetchrow(
            """
            INSERT INTO distro_requests
              (distro_name, release_name, format, base_url, description, contact_info)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, distro_name, release_name, status, created_at
            """,
            payload.distro_name,
            payload.release_name,
            payload.format,
            payload.base_url,
            payload.description,
            payload.contact_info,
        )
    result = dict(row)
    result["created_at"] = result["created_at"].isoformat()
    return result


@router.get("/distros/requests")
async def list_distro_requests(
    user: Annotated[dict, Depends(require_role("maintainer"))],
    status: str | None = None,
) -> dict:
    """List distro requests (maintainer+)."""
    pool = get_pool()
    filters = ["TRUE"]
    params: list = []
    if status:
        params.append(status)
        filters.append(f"status = ${len(params)}")
    where = " AND ".join(filters)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM distro_requests WHERE {where} ORDER BY created_at DESC",
            *params,
        )

    def _fmt(r: dict) -> dict:
        for k in ("created_at", "updated_at"):
            if r.get(k):
                r[k] = r[k].isoformat()
        return r

    return {"requests": [_fmt(dict(r)) for r in rows]}


@router.patch("/distros/requests/{request_id}")
async def update_distro_request(
    request_id: int,
    status: str,
    user: Annotated[dict, Depends(require_role("maintainer"))],
) -> dict:
    """Approve, reject, or mark a distro request as implemented (maintainer+)."""
    if status not in ("approved", "rejected", "implemented"):
        raise HTTPException(400, "status must be one of: approved, rejected, implemented.")
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE distro_requests
            SET status = $1, reviewed_by = $2, updated_at = now()
            WHERE id = $3
            RETURNING id, distro_name, status
            """,
            status,
            user["id"],
            request_id,
        )
    if row is None:
        raise HTTPException(404, f"Request #{request_id} not found.")
    return dict(row)
