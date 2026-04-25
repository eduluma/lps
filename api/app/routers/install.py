from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..db import get_pool

router = APIRouter(tags=["install"])

# Default ranking when distro=auto and no UA hint is available.
DEFAULT_RANK = ["debian", "ubuntu", "fedora", "alpine", "arch"]


@router.get("/install/{name}")
async def install_command(
    name: str,
    distro: str = Query("auto"),
    fmt: str = Query("text", pattern="^(text|json)$"),
):
    pool = get_pool()
    async with pool.acquire() as conn:
        if distro == "auto":
            row = await conn.fetchrow(
                """
                SELECT p.distro, p.release, p.package_name, d.install_command_template
                FROM packages p
                JOIN distros d ON d.name = p.distro
                WHERE p.package_name = $1
                ORDER BY array_position($2::text[], p.distro) NULLS LAST,
                         p.release DESC
                LIMIT 1
                """,
                name,
                DEFAULT_RANK,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT p.distro, p.release, p.package_name, d.install_command_template
                FROM packages p
                JOIN distros d ON d.name = p.distro
                WHERE p.package_name = $1 AND p.distro = $2
                ORDER BY p.release DESC
                LIMIT 1
                """,
                name,
                distro,
            )
    if row is None:
        raise HTTPException(404, f"no install candidate for '{name}'")
    cmd = row["install_command_template"].format(pkg=row["package_name"])
    if fmt == "text":
        return PlainTextResponse(cmd + "\n")
    return {
        "name": name,
        "distro": row["distro"],
        "release": row["release"],
        "command": cmd,
    }
