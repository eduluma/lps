#!/usr/bin/env python3
"""Promote a user to admin role by token.

Usage:
    python promote_admin.py <token>
    python promote_admin.py  # reads token from LPS_PROMOTE_TOKEN env var
"""

from __future__ import annotations

import asyncio
import os
import sys


async def main() -> None:
    token = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("LPS_PROMOTE_TOKEN", "")
    if not token:
        print("Usage: promote_admin.py <token>", file=sys.stderr)
        sys.exit(1)

    import asyncpg

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        row = await conn.fetchrow(
            "UPDATE users SET role = 'admin' WHERE token = $1 RETURNING email, role",
            token,
        )
        if row:
            print(f"Promoted {row['email']} → role={row['role']}")
        else:
            print("ERROR: no user found with that token", file=sys.stderr)
            sys.exit(1)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

