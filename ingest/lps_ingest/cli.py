"""CLI: `python -m lps_ingest.cli debian bookworm`
`python -m lps_ingest.cli worker`           (queue polling mode)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import asyncpg

from . import alpine, arch, debian, fedora, opensuse
from .config import DATABASE_URL
from .upsert import upsert_packages

log = logging.getLogger(__name__)

POLL_INTERVAL = int(os.getenv("INGEST_POLL_INTERVAL", "30"))  # seconds


async def run(distro: str, release: str, component: str, arch_name: str) -> int:
    if distro in ("debian", "ubuntu"):
        records = list(debian.ingest(distro, release, component, arch_name))
    elif distro == "alpine":
        records = list(alpine.ingest(release))
    elif distro == "arch":
        records = list(arch.ingest(release))
    elif distro == "fedora":
        records = list(fedora.ingest(release))
    elif distro == "opensuse":
        records = list(opensuse.ingest(release))
    else:
        print(f"distro '{distro}' not implemented yet", file=sys.stderr)
        return 1
    n = await upsert_packages(records)
    print(f"upserted {n} packages from {distro}/{release}")
    return 0


async def _claim_job(conn: asyncpg.Connection) -> dict | None:
    """Atomically claim one pending ingest job. Returns the job row or None."""
    return await conn.fetchrow(
        """
        UPDATE ingest_jobs
        SET status = 'running', started_at = now()
        WHERE id = (
            SELECT id FROM ingest_jobs
            WHERE status = 'pending'
            ORDER BY created_at
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, distro, release
        """
    )


async def _finish_job(
    conn: asyncpg.Connection,
    job_id: int,
    *,
    status: str,
    packages_upserted: int | None = None,
    error_message: str | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE ingest_jobs
        SET status = $1, finished_at = now(),
            packages_upserted = $2, error_message = $3
        WHERE id = $4
        """,
        status,
        packages_upserted,
        error_message,
        job_id,
    )


async def worker_loop() -> None:
    """Poll ingest_jobs for pending work and execute each job."""
    log.info("Ingest worker started (poll interval: %ds)", POLL_INTERVAL)
    db = await asyncpg.connect(DATABASE_URL)
    try:
        while True:
            async with db.transaction():
                job = await _claim_job(db)

            if job is None:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            job_id, distro, release = job["id"], job["distro"], job["release"]
            log.info("Running job #%d: %s/%s", job_id, distro, release)
            try:
                # Reuse run() — component/arch defaults are fine for queue jobs
                await run(distro, release, "main", "amd64")
                # Count upserted by querying the job after run(); simpler: pass n back
                # For now read from stdout isn't practical — we'll store count via a
                # wrapper that captures the return value of upsert_packages directly.
                n = await _count_packages(db, distro, release)
                await _finish_job(db, job_id, status="done", packages_upserted=n)
                log.info("Job #%d done (%d packages)", job_id, n)
            except Exception as exc:  # noqa: BLE001
                log.error("Job #%d failed: %s", job_id, exc)
                await _finish_job(db, job_id, status="failed", error_message=str(exc))
    finally:
        await db.close()


async def _count_packages(conn: asyncpg.Connection, distro: str, release: str) -> int:
    return (
        await conn.fetchval(
            "SELECT COUNT(*) FROM packages WHERE distro = $1 AND release = $2",
            distro,
            release,
        )
        or 0
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Fast-path: direct mode — `lps-ingest <distro> <release> [--component x] [--arch y]`
    # Must be checked before argparse so "debian" isn't consumed by the subparser slot.
    if len(sys.argv) >= 3 and sys.argv[1] not in ("worker", "-h", "--help"):
        p = argparse.ArgumentParser("lps-ingest")
        p.add_argument("distro")
        p.add_argument("release")
        p.add_argument("--component", default="main")
        p.add_argument("--arch", default="amd64")
        args = p.parse_args()
        sys.exit(asyncio.run(run(args.distro, args.release, args.component, args.arch)))

    p = argparse.ArgumentParser("lps-ingest")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("worker", help="Run as a persistent queue worker")
    p.add_argument("distro", nargs="?", help="Distro name (direct mode)")
    p.add_argument("release", nargs="?", help="Release name (direct mode)")
    p.add_argument("--component", default="main")
    p.add_argument("--arch", default="amd64")

    args = p.parse_args()

    if args.cmd == "worker":
        asyncio.run(worker_loop())
    elif args.distro and args.release:
        sys.exit(asyncio.run(run(args.distro, args.release, args.component, args.arch)))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
