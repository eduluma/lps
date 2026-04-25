from __future__ import annotations

import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, field_validator

from ..db import get_pool

# ── Role ordering ─────────────────────────────────────────────────────────────
_ROLE_RANK = {"viewer": 0, "maintainer": 1, "admin": 2}


async def _get_current_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    """Resolve Bearer token → user row. Raises 401 if missing/invalid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header.")
    token = authorization.removeprefix("Bearer ").strip()
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, display_name, email, account_type, role, plan, plan_expires_at "
            "FROM users WHERE token = $1",
            token,
        )
    if row is None:
        raise HTTPException(401, "Invalid token.")
    return dict(row)


def require_role(min_role: str):
    """FastAPI dependency: requires the caller to have at least *min_role*."""
    async def _dep(user: Annotated[dict, Depends(_get_current_user)]) -> dict:
        if _ROLE_RANK.get(user["role"], 0) < _ROLE_RANK.get(min_role, 99):
            raise HTTPException(403, f"Requires role '{min_role}' or higher.")
        return user
    return _dep

router = APIRouter(tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str
    display_name: str
    account_type: str = "individual"

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address.")
        if len(v) > 254:
            raise ValueError("Email must be ≤ 254 characters.")
        return v

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 100:
            raise ValueError("Display name must be 1–100 characters.")
        return v

    @field_validator("account_type")
    @classmethod
    def _type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("individual", "org"):
            raise ValueError("account_type must be 'individual' or 'org'.")
        return v


@router.post("/auth/register", status_code=201)
async def register(payload: RegisterIn) -> dict:
    """Register and receive a permanent API token.

    The token is shown once in the response — save it.  Use it as:

        Authorization: Bearer <token>

    on any API request that accepts authenticated callers.
    """
    token = "lps_" + secrets.token_urlsafe(32)
    pool = get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", payload.email)
        if existing:
            raise HTTPException(
                409,
                "An account with this email already exists. "
                "If you have lost your token, contact support.",
            )
        row = await conn.fetchrow(
            """
            INSERT INTO users (email, display_name, account_type, token)
            VALUES ($1, $2, $3, $4)
            RETURNING id, display_name, account_type, token, created_at
            """,
            payload.email,
            payload.display_name,
            payload.account_type,
            token,
        )

    result = dict(row)
    result["created_at"] = result["created_at"].isoformat()
    return result


@router.get("/auth/me")
async def me(user: Annotated[dict, Depends(_get_current_user)]) -> dict:
    """Return the current user's profile (role, plan, display_name)."""
    return {
        "id": user["id"],
        "display_name": user["display_name"],
        "account_type": user["account_type"],
        "role": user["role"],
        "plan": user["plan"],
    }
