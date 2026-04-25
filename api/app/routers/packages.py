from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..db import get_pool

router = APIRouter(tags=["packages"])


@router.get("/packages")
async def list_packages(
    distro: str | None = None,
    release: str | None = None,
    q: str | None = Query(None, min_length=1, max_length=100),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    pool = get_pool()
    sql = """
        SELECT distro, release, repo, package_name, version, description
        FROM packages
        WHERE ($1::text IS NULL OR distro = $1)
          AND ($2::text IS NULL OR release = $2)
          AND ($3::text IS NULL OR package_name ILIKE '%' || $3 || '%')
        ORDER BY package_name
        LIMIT $4
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, distro, release, q, limit)
    return {"results": [dict(r) for r in rows]}


@router.get("/packages/{distro}/{release}/{name}")
async def get_package(distro: str, release: str, name: str) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM packages WHERE distro = $1 AND release = $2 "
            "AND package_name = $3 LIMIT 1",
            distro,
            release,
            name,
        )
    if row is None:
        raise HTTPException(404, "package not found")
    return dict(row)
