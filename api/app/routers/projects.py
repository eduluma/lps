from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..db import get_pool

router = APIRouter(tags=["projects"])


@router.get("/projects/{name}")
async def get_project(name: str) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        proj = await conn.fetchrow(
            "SELECT * FROM projects WHERE normalized_name = $1", name.lower()
        )
        if proj is None:
            # No project row yet — try to serve directly from packages table.
            # This covers packages that haven't been mapped to a project (Phase 1).
            pkgs = await conn.fetch(
                "SELECT distro, release, repo, package_name, version, description, "
                "homepage_url, download_url, last_seen "
                "FROM packages "
                "WHERE project_id IS NULL AND lower(package_name) = $1 "
                "ORDER BY distro, release",
                name.lower(),
            )
            if not pkgs:
                raise HTTPException(404, f"project '{name}' not found")
            # Synthesise a minimal project object from the first package row
            first = pkgs[0]
            synthetic_project = {
                "id": None,
                "canonical_name": first["package_name"],
                "normalized_name": name.lower(),
                "description": first["description"],
                "homepage_url": first["homepage_url"],
                "source_url": None,
            }
            return {"project": synthetic_project, "packages": [dict(p) for p in pkgs]}

        pkgs = await conn.fetch(
            "SELECT distro, release, repo, package_name, version, description, "
            "homepage_url, download_url, last_seen "
            "FROM packages "
            "WHERE project_id = $1 "
            "   OR (project_id IS NULL AND lower(package_name) = $2) "
            "ORDER BY distro, release",
            proj["id"],
            proj["normalized_name"],
        )
    return {"project": dict(proj), "packages": [dict(p) for p in pkgs]}
