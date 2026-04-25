# GitHub Copilot — LPS Project Instructions

Read this file at the start of every session. Follow these rules for all code
suggestions, edits, and agent actions.

---

## Project overview

**LPS (Linux Package Search)** — a unified, brew.sh-style package search for
Linux. One query returns a single working install command across Debian, Ubuntu,
Alpine, Arch, Fedora, and openSUSE.

Public URL: `https://lps.eduluma.org`  
Repo: `eduluma.org/lps`

---

## Stack

| Layer    | Technology                                    |
| -------- | --------------------------------------------- |
| DB       | PostgreSQL 16 (`pg_trgm` GIN index)           |
| API      | FastAPI + asyncpg (uvicorn), `/api/v1/`       |
| Ingest   | Python workers (`lps_ingest`), on-demand      |
| Frontend | Astro 4 (`output: "server"`) + Tailwind CSS   |
| CLI      | Go single binary (`cli/`), goreleaser → Gitea |
| Dev env  | Docker Compose (`db`, `api`, `web`, `ingest`) |
| K8s      | Docker Desktop k8s on m1studio, Helm chart    |
| Tunnel   | Cloudflare Tunnel (`cloudflared`) — optional  |
| CDN      | Cloudflare (in front of API + frontend)       |

---

## Traffic flow

```text
Browser / CLI
    │
    ▼
Cloudflare CDN  ──(cache hit)──▶  cached response
    │ cache miss
    ▼
Cloudflare Tunnel (cloudflared)
    │
    ├──▶  /api/v1/*  ──▶  FastAPI (uvicorn :8000)  ──▶  PostgreSQL :5432
    │
    └──▶  /*          ──▶  Astro dev/preview (:4321)
              │ SSR frontmatter fetches
              └──▶  http://api:8000  (Docker service name, API_INTERNAL_BASE)
```

**Important env var split:**

| Variable            | Value (dev)                    | Used by               |
| ------------------- | ------------------------------ | --------------------- |
| `PUBLIC_API_BASE`   | `http://localhost:8000/api/v1` | Browser `<script>`    |
| `API_INTERNAL_BASE` | `http://api:8000/api/v1`       | Astro SSR frontmatter |

Browser-side scripts always use `PUBLIC_API_BASE` (resolves from the user's
machine). Astro server-side (`---` frontmatter) must use `API_INTERNAL_BASE`
so requests stay inside the Docker network and don't hit localhost:8000 (which
doesn't exist inside the container).

---

## Key design decisions

- **Astro `output: "server"`** — dynamic routes like `/p/[name]` can't use
  `getStaticPaths()` for ~70k packages; server mode lets the dev server render
  them on-demand.
- **Client-side data fetching for search/distros/package pages** — pass
  server-side data (e.g. `Astro.params.name`) via `data-*` attributes to
  `<script>` blocks; never use `window.location` when the param is already
  available in the frontmatter.
- **`packages.project_id` is NULL for all ingested packages** (Phase 1). The
  `/projects/{name}` API falls back to `lower(package_name) = normalized_name`
  until the mapping pipeline (Phase 2) is built.
- **`project_package_map`** is a Phase 2 concern — see the section below.

---

## `project_package_map` — what it is and when it matters

`project_package_map` is a **many-to-many join table** between `projects` and
`packages`, with a `confidence_score` (0–1) and `is_primary` flag. It is NOT
seeded manually — it gets **populated by an automated mapping pipeline** that:

1. Matches `packages.package_name` → `projects.normalized_name` (exact + fuzzy)
2. Matches `packages.homepage_url` → `projects.homepage_url`
3. Resolves aliases (`aliases` table)
4. Writes rows with confidence scores

Until that pipeline runs:
- `packages.project_id` is `NULL`
- `/api/v1/projects/{name}` uses a fallback: `lower(package_name) = normalized_name`
- `/p/{name}` pages still work via that fallback

**Phase 2 task**: build `lps_ingest/map_projects.py` that runs after each ingest
and populates both `packages.project_id` and `project_package_map`.

---

## Coding conventions

- **Python**: `from __future__ import annotations`, type hints throughout,
  asyncpg (never SQLAlchemy ORM), `uv` for package management.
- **TypeScript/Astro**: strict mode, no `innerHTML` with untrusted data,
  DOM manipulation via `createElement` / `textContent` in `<script>` blocks.
- **SQL**: raw SQL via asyncpg `conn.fetch` / `conn.fetchrow`; migrations in
  `db/migrations/` (plain `.sql` files); Alembic wraps them.
- **Commits**: conventional-commit style (`fix(scope):`, `feat(scope):`,
  `chore:`). One logical change per commit.

---

## Agent workflow rules

1. **Read `TODO.md` before starting any task.** Mark the relevant item(s) with
   a note that work is in progress.
2. **Update `TODO.md` after completing a task.** Check off done items; add new
   items discovered during the work.
3. **Commit after every meaningful, self-contained change:**
   ```bash
   git add -A && git commit -m "fix(scope): short description"
   ```
   Use separate commits for separate concerns (API fix, frontend fix, docs).
4. **Never leave the repo in a broken state.** Verify with a quick `curl` or
   log check before committing.
5. **Do not add features beyond what was asked.** Minimal, targeted changes.

---

## Common commands

```bash
# Start everything
docker compose up -d

# Tail logs
docker compose logs -f web
docker compose logs -f api

# Run migrations
docker compose run --rm migrate

# Ingest Debian bookworm
docker compose run --rm ingest debian bookworm

# psql
psql postgresql://lps:lps@localhost:5432/lps

# Check API
curl http://localhost:8000/healthz
curl "http://localhost:8000/api/v1/search?q=curl"
curl "http://localhost:8000/api/v1/projects/curl"

# SSH to m1studio (home server running Docker Desktop k8s)
ssh 192.168.1.72 -l admin

# K8s deploy (from repo root)
task k8s:build       # build + tag all images
task k8s:push        # push to gitea.eduluma.org/eduluma/lps
task k8s:deploy      # helm upgrade --install lps-dev
task k8s:logs        # tail all lps-dev pod logs
```

---

## File map (key files)

```text
api/app/
  main.py          — FastAPI app + router registration
  db.py            — asyncpg pool init/teardown
  routers/
    search.py      — GET /search  (pg_trgm + ILIKE fallback)
    projects.py    — GET /projects/{name}  (+ package_name fallback)
    distros.py     — GET /distros, /stats
    install.py     — GET /install/{name}

web/src/
  astro.config.mjs — output:"server", tailwind
  lib/api.ts       — API_BASE (prefers API_INTERNAL_BASE for SSR)
  pages/
    index.astro    — hero + search box (SSR stats via API_INTERNAL_BASE)
    search.astro   — client-side search results
    distros.astro  — client-side distro grid
    p/[name].astro — client-side package page (data-pkg attr → script)

ingest/lps_ingest/
  cli.py           — entrypoint: `python -m lps_ingest.cli <distro> <release>`
  debian.py        — Debian/Ubuntu package list parser
  upsert.py        — asyncpg bulk upsert into packages table
```
