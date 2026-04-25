# LPS — Distro Onboarding & Triggered Ingest Jobs

## Overview

This document covers two related features, implemented across two sessions:

- **Session 1 (this one):** Schema, auth roles, ingest job queue + worker polling, `/distros` last-ingest timestamps.
- **Session 2 (next):** Distro request form (API + frontend), ingest trigger UI, distro card updates.

---

## How Option C covers Options A and B

Option C is a `distro_sources` table — one row per (distro, release) that the
ingest worker knows how to pull.

| Intake channel       | What happens                                                                                                                                                                                                                                          |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A — PR**           | The contributor opens a PR that adds a row to `db/migrations/XXXX_distro_sources.up.sql`. If the format is `apt`, `rpm`, `apk`, or `aur`, **no Python code is needed** — the worker already handles it. A new format requires a PR with a parser too. |
| **B — Request form** | A distro maintainer fills the `/distros/request` form on the site. An LPS maintainer reviews it and, if approved, inserts the row into `distro_sources` via the admin API. The form is the intake; `distro_sources` is the canonical config.          |

In both cases the ingest worker reads from `distro_sources` — it never has
hardcoded URL logic for sources defined there. Custom/special distros (e.g.
Arch AUR, NixOS) still need a Python module; that's the only time a code PR is
required.

---

## Session 1 — Schema & Backend

### Migration 0004 adds

#### `users` columns

| Column            | Type        | Notes                                                                          |
| ----------------- | ----------- | ------------------------------------------------------------------------------ |
| `role`            | TEXT        | `viewer` (default) · `maintainer` · `admin`                                    |
| `plan`            | TEXT        | `free` (default) · `pro` · `enterprise` — monetization-ready, not enforced yet |
| `plan_expires_at` | TIMESTAMPTZ | NULL = no expiry; set for paid plans                                           |

`role` gates ingest triggers. `plan` is reserved for future rate-limit tiers
and advanced features; nothing checks it yet, but the column is there so we
don't need another migration later.

#### `distro_sources`

Config-driven registry of (distro, release) pairs the worker can pull.

```
distro_sources
├── id
├── distro          → must match distros.name
├── release         → e.g. "bookworm", "41", "tumbleweed"
├── format          → apt | rpm | apk | aur | custom
├── base_url        → e.g. "https://dl.fedoraproject.org/..."
├── extra_config    → JSONB — format-specific options (component, arch, etc.)
├── enabled         → soft-disable without deleting
├── added_by        → users.id FK
└── created_at
```

For `apt`, `extra_config` holds `{"component": "main", "arch": "amd64"}`.
For `rpm`, no extra config needed.
For `custom`, the worker falls back to the existing Python module for that distro.

#### `distro_requests`

Community intake for new distros.

```
distro_requests
├── id
├── distro_name     → proposed distro name
├── release_name    → proposed release (optional)
├── format          → apt | rpm | apk | aur | other
├── base_url        → where the package index lives
├── description     → free-text from requester
├── contact_info    → optional email / handle for follow-up
├── status          → pending | approved | rejected | implemented
├── user_id         → users.id FK (NULL = anonymous)
├── reviewed_by     → users.id FK of maintainer who acted
├── source_id       → distro_sources.id FK (set when implemented)
└── created_at / updated_at
```

#### `ingest_jobs`

Job queue + permanent audit trail.

```
ingest_jobs
├── id
├── distro
├── release
├── source_id       → distro_sources.id FK (NULL = legacy CLI trigger)
├── status          → pending | running | done | failed
├── triggered_by    → users.id FK (NULL = scheduled/CLI)
├── packages_upserted  INT
├── error_message   TEXT
├── started_at      TIMESTAMPTZ
├── finished_at     TIMESTAMPTZ
└── created_at      TIMESTAMPTZ
```

**Duplicate prevention:** a `UNIQUE` partial index on `(distro, release)` where
`status IN ('pending', 'running')` means you can't queue the same distro/release
twice while it's already pending or running.

**Cooldown:** the API rejects a new trigger if the last `done` job for that
distro/release finished within 6 hours (configurable via `INGEST_COOLDOWN_HOURS`).

**Abuse prevention:** only `role IN ('maintainer', 'admin')` can enqueue.
Future: tie to `plan` for per-tier quotas.

---

## Session 1 — API endpoints

### Auth helper

`api/app/routers/auth.py` grows a `require_role(min_role)` dependency that
reads the `Authorization: Bearer <token>` header, looks up the user, and
raises 401/403 as needed.

### `POST /api/v1/ingest/{distro}/{release}`

- Requires `maintainer` or `admin`
- Checks cooldown (last done job < 6h → 429)
- Checks no active job exists (pending/running → 409 with job id)
- Inserts `ingest_jobs` row with `status='pending'`
- Returns `{job_id, status, distro, release}`

### `GET /api/v1/ingest/jobs`

- Requires `maintainer` or `admin`
- Query params: `distro`, `release`, `status`, `limit` (default 50)
- Returns recent jobs newest-first

### `GET /api/v1/ingest/jobs/{job_id}`

- Public (job status is not sensitive)
- Returns single job row

### `GET /api/v1/distros` (updated)

- Each distro object gains `last_ingest` — timestamp of the most recent
  `done` job across all its releases, plus `last_ingest_release`.

---

## Session 1 — Ingest worker changes

The worker gets a new `worker` sub-command that runs a polling loop:

```
python -m lps_ingest.cli worker [--poll-interval 30]
```

On each tick:
1. Claims one `pending` job atomically (`UPDATE ... SET status='running' WHERE id = (SELECT id FROM ingest_jobs WHERE status='pending' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *`)
2. Runs the ingest
3. Updates the job to `done` or `failed` with counts / error message

The existing `python -m lps_ingest.cli <distro> <release>` still works for
manual / CI use.

`docker-compose.yml` will gain an `ingest-worker` service that runs the
polling loop continuously alongside the API.

---

## Session 2 — Distro request form

- `POST /api/v1/distros/request` — public (anon OK), inserts into `distro_requests`
- `GET /api/v1/distros/requests` — maintainer+ only, lists pending requests
- `PATCH /api/v1/distros/requests/{id}` — maintainer+ only, approve/reject
- Frontend: `/distros` page gets a "Request a distro" button → modal form
- Frontend: `/distros` cards show "Last indexed: 3 days ago" using `last_ingest`
- Frontend: maintainers see a ⟳ trigger button on each card (shown only when
  token is stored in localStorage and role can be inferred from a `/auth/me`
  endpoint to be added in session 2)

---

## Monetization notes (no enforcement yet)

These columns/patterns are in place so future tiers don't need schema changes:

| Thing                       | Where          | Future use                                                   |
| --------------------------- | -------------- | ------------------------------------------------------------ |
| `users.plan`                | migration 0004 | Gate advanced search, higher rate limits, API key management |
| `users.plan_expires_at`     | migration 0004 | Subscription expiry checks                                   |
| `users.role = 'maintainer'` | migration 0004 | Could become a paid feature for org accounts                 |
| `ingest_jobs.triggered_by`  | migration 0004 | Per-user ingest quota by plan                                |
| `distro_requests.user_id`   | migration 0004 | Attribution, priority queue for paid orgs                    |
