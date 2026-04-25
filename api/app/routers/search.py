from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import get_pool

router = APIRouter(tags=["search"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=100),
    distro: str | None = None,
    release: str | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """Search packages using pg_trgm similarity + prefix match.

    Uses the GIN index on package_name for fast trigram lookups.
    Results are ranked by similarity score descending.
    """
    pool = get_pool()
    sql = """
        SELECT distro, release, package_name, version, description,
               similarity(package_name, $1) AS score
        FROM packages
        WHERE package_name % $1
          AND ($2::text IS NULL OR distro = $2)
          AND ($3::text IS NULL OR release = $3)
        ORDER BY score DESC, package_name
        LIMIT $4
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, q, distro, release, limit)
    # Fall back to ILIKE if trigram finds nothing (query too short / low similarity)
    if not rows:
        sql_fallback = """
            SELECT distro, release, package_name, version, description,
                   1.0::float AS score
            FROM packages
            WHERE package_name ILIKE $1
              AND ($2::text IS NULL OR distro = $2)
              AND ($3::text IS NULL OR release = $3)
            ORDER BY package_name
            LIMIT $4
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql_fallback, f"{q}%", distro, release, limit)
    return {
        "query": q,
        "results": [dict(r) for r in rows],
    }
