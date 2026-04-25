from __future__ import annotations

from collections.abc import Iterable

import asyncpg

from .config import DATABASE_URL
from .models import PackageRecord

UPSERT_SQL = """
INSERT INTO packages (
  distro, release, repo, arch, package_name, version,
  description, homepage_url, maintainer, download_url, size_bytes,
  first_seen, last_seen
) VALUES (
  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11, NOW(), NOW()
)
ON CONFLICT (distro, release, repo, package_name, arch) DO UPDATE SET
  version = EXCLUDED.version,
  description = EXCLUDED.description,
  homepage_url = EXCLUDED.homepage_url,
  maintainer = EXCLUDED.maintainer,
  download_url = EXCLUDED.download_url,
  size_bytes = EXCLUDED.size_bytes,
  last_seen = NOW(),
  updated_at = NOW();
"""


async def upsert_packages(records: Iterable[PackageRecord]) -> int:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        n = 0
        async with conn.transaction():
            for r in records:
                await conn.execute(
                    UPSERT_SQL,
                    r.distro, r.release, r.repo, r.arch, r.package_name, r.version,
                    r.description, r.homepage_url, r.maintainer, r.download_url, r.size_bytes,
                )
                n += 1
        return n
    finally:
        await conn.close()
