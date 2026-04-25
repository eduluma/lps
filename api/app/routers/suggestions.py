from __future__ import annotations

import logging
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from ..db import get_pool

log = logging.getLogger(__name__)

router = APIRouter(tags=["suggestions"])

# ── Constants ────────────────────────────────────────────────────────────────

KNOWN_DISTROS: frozenset[str] = frozenset(
    {"debian", "ubuntu", "alpine", "arch", "fedora", "opensuse"}
)

# Debian/rpm-style package name rules (lower-case, no spaces)
_PKG_RE = re.compile(r"^[a-z0-9][a-z0-9._+\-]*$")
_RELEASE_RE = re.compile(r"^[a-zA-Z0-9._\-]+$")
# Anonymous vs token-holder daily submission limits
ANON_DAILY_LIMIT = 5
USER_DAILY_LIMIT = 20


# ── Helpers ───────────────────────────────────────────────────────────────────


def _client_ip(request: Request) -> str:
    """Return the real client IP, honouring X-Forwarded-For (Cloudflare / cloudflared)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _resolve_token(request: Request, conn) -> int | None:
    """Return user_id for a valid Bearer token, or None if absent/invalid."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    if not token.startswith("lps_"):
        return None
    return await conn.fetchval("SELECT id FROM users WHERE token = $1", token)


# ── Pydantic models ───────────────────────────────────────────────────────────


class SuggestionIn(BaseModel):
    """Strict template that every user submission must satisfy."""

    package_name: str
    distro: str
    release: str
    install_cmd: str
    description: str
    homepage_url: str | None = None
    # Honeypot — legitimate browsers leave this empty; bots fill it in
    website: str = ""

    @field_validator("package_name")
    @classmethod
    def _pkg(cls, v: str) -> str:
        v = v.strip().lower()
        if not _PKG_RE.match(v):
            raise ValueError(
                "Package name must be lowercase and contain only letters, digits, "
                "dots, hyphens, underscores, or plus signs."
            )
        if len(v) > 100:
            raise ValueError("Package name must be ≤ 100 characters.")
        return v

    @field_validator("distro")
    @classmethod
    def _distro(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in KNOWN_DISTROS:
            raise ValueError(f"Unknown distro. Choose one of: {', '.join(sorted(KNOWN_DISTROS))}.")
        return v

    @field_validator("release")
    @classmethod
    def _release(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 50:
            raise ValueError("Release must be 1–50 characters.")
        if not _RELEASE_RE.match(v):
            raise ValueError("Release may only contain letters, digits, dots, or hyphens.")
        return v

    @field_validator("install_cmd")
    @classmethod
    def _install(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 200:
            raise ValueError("Install command must be 1–200 characters.")
        return v

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 200:
            raise ValueError("Description must be 1–200 characters.")
        return v

    @field_validator("homepage_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        if not v:
            return None
        v = v.strip()
        if not re.match(r"^https?://", v):
            raise ValueError("Homepage URL must start with http:// or https://.")
        if len(v) > 500:
            raise ValueError("Homepage URL must be ≤ 500 characters.")
        return v


# ── URL relevance check ───────────────────────────────────────────────────────

_URL_FETCH_TIMEOUT = 5.0  # seconds
_URL_MAX_BYTES = 256_000  # read at most 256 KB of response body


async def _url_mentions_package(url: str, package_name: str) -> tuple[bool, str]:
    """Fetch *url* and return (mentions, reason).

    Returns ``(True, "")`` if the package name appears in the page text, or if
    the URL is unreachable (we give the benefit of the doubt on fetch errors).
    Returns ``(False, reason)`` only when the page is reachable but the name is
    clearly absent.
    """
    # Build a set of tokens to look for: full name + stem without trailing digits/version
    needle = package_name.lower().replace("-", "").replace("_", "").replace("+", "")
    needles = {package_name.lower(), needle}

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=_URL_FETCH_TIMEOUT,
            headers={"User-Agent": "lps-bot/1.0 (+https://lps.eduluma.org)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            # Read limited bytes to avoid pulling down huge pages
            content = resp.text[:_URL_MAX_BYTES].lower()
    except httpx.HTTPStatusError as exc:
        log.warning("URL relevance check: HTTP %s for %s", exc.response.status_code, url)
        # 4xx from the remote — the URL is probably wrong, but don't block submission
        return True, ""
    except Exception as exc:  # noqa: BLE001
        log.warning("URL relevance check: fetch error for %s: %s", url, exc)
        # Network/DNS errors — give benefit of the doubt
        return True, ""

    for n in needles:
        if n in content:
            return True, ""

    return (
        False,
        f"The homepage URL was fetched but doesn't appear to mention "
        f"'{package_name}'. Please double-check the URL.",
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/suggestions")
async def list_suggestions(
    limit: int = 20,
    offset: int = 0,
    q: str | None = None,
    distro: str | None = None,
) -> dict:
    """Return pending suggestions sorted by vote count (highest first).

    Optional filters:
    - ``q``: case-insensitive substring match on ``package_name``
    - ``distro``: exact distro name
    """
    limit = max(1, min(limit, 100))

    filters = ["s.status = 'pending'"]
    args: list = []

    if q:
        args.append(f"%{q.lower()}%")
        filters.append(f"lower(s.package_name) LIKE ${len(args)}")
    if distro:
        args.append(distro.lower())
        filters.append(f"lower(s.distro) = ${len(args)}")

    where = " AND ".join(filters)

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                s.id,
                s.package_name,
                s.distro,
                s.release,
                s.install_cmd,
                s.description,
                s.homepage_url,
                s.status,
                s.created_at,
                COUNT(v.suggestion_id)::int AS vote_count,
                u.display_name AS submitter_name,
                u.account_type  AS submitter_type
            FROM suggestions s
            LEFT JOIN suggestion_votes v ON v.suggestion_id = s.id
            LEFT JOIN users u ON u.id = s.user_id
            WHERE {where}
            GROUP BY s.id, u.display_name, u.account_type
            ORDER BY vote_count DESC, s.created_at DESC
            LIMIT ${len(args) + 1} OFFSET ${len(args) + 2}
            """,
            *args,
            limit,
            offset,
        )
        total: int = await conn.fetchval(
            f"SELECT COUNT(*)::int FROM suggestions s WHERE {where}",
            *args,
        )

    return {
        "suggestions": [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/suggestions", status_code=201)
async def create_suggestion(payload: SuggestionIn, request: Request) -> dict:
    """Submit a new package suggestion.

    Checks:
    - Honeypot field (silently swallow bots)
    - Daily rate limit (20/day with token, 5/day anonymous)
    - Duplicate pending suggestion for same (package, distro, release)
    """
    # Honeypot — accept silently so bots think they succeeded
    if payload.website:
        return {"id": 0, "status": "pending"}

    ip = _client_ip(request)
    pool = get_pool()
    async with pool.acquire() as conn:
        # Resolve optional bearer token
        user_id = await _resolve_token(request, conn)
        daily_limit = USER_DAILY_LIMIT if user_id else ANON_DAILY_LIMIT

        # Rate limit — key on user_id when authenticated, else IP
        if user_id:
            recent: int = await conn.fetchval(
                "SELECT COUNT(*)::int FROM suggestions "
                "WHERE user_id = $1 AND created_at > now() - interval '24 hours'",
                user_id,
            )
        else:
            recent = await conn.fetchval(
                "SELECT COUNT(*)::int FROM suggestions "
                "WHERE submitter_ip = $1 AND created_at > now() - interval '24 hours'",
                ip,
            )
        if recent >= daily_limit:
            anon_hint = " Register for a token to raise your limit." if not user_id else ""
            raise HTTPException(
                429,
                f"You've submitted too many suggestions today. "
                f"Limit is {daily_limit} per 24 hours.{anon_hint}",
            )

        # Check for an existing pending suggestion for the same (package, distro, release)
        dup_id = await conn.fetchval(
            "SELECT id FROM suggestions "
            "WHERE lower(package_name) = $1 AND distro = $2 AND lower(release) = $3 "
            "  AND status = 'pending'",
            payload.package_name,
            payload.distro,
            payload.release.lower(),
        )
        if dup_id is not None:
            raise HTTPException(
                409,
                f"A pending suggestion for '{payload.package_name}' on "
                f"{payload.distro}/{payload.release} already exists — upvote it!",
            )
    # user_id is now in scope for the insert below

    # URL relevance check (outside the DB connection to avoid holding it open)
    if payload.homepage_url:
        ok, reason = await _url_mentions_package(payload.homepage_url, payload.package_name)
        if not ok:
            raise HTTPException(422, reason)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO suggestions
              (package_name, distro, release, install_cmd, description,
               homepage_url, submitter_ip, user_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, status
            """,
            payload.package_name,
            payload.distro,
            payload.release,
            payload.install_cmd,
            payload.description,
            payload.homepage_url,
            ip,
            user_id,
        )

    return dict(row)


@router.post("/suggestions/{suggestion_id}/vote")
async def vote_suggestion(suggestion_id: int, request: Request) -> dict:
    """Cast or retract a vote (toggle). Returns the new vote count."""
    ip = _client_ip(request)
    pool = get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM suggestions WHERE id = $1 AND status = 'pending'",
            suggestion_id,
        )
        if not exists:
            raise HTTPException(404, "Suggestion not found.")

        # Toggle: try to insert; if already voted, delete instead
        inserted = await conn.fetchval(
            """
            WITH ins AS (
              INSERT INTO suggestion_votes (suggestion_id, voter_ip)
              VALUES ($1, $2)
              ON CONFLICT DO NOTHING
              RETURNING 1
            )
            SELECT COUNT(*) FROM ins
            """,
            suggestion_id,
            ip,
        )
        if not inserted:
            # Already voted — retract
            await conn.execute(
                "DELETE FROM suggestion_votes WHERE suggestion_id = $1 AND voter_ip = $2",
                suggestion_id,
                ip,
            )

        vote_count: int = await conn.fetchval(
            "SELECT COUNT(*)::int FROM suggestion_votes WHERE suggestion_id = $1",
            suggestion_id,
        )

    return {"vote_count": vote_count, "voted": bool(inserted)}
