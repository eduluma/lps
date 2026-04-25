# LPS — Master TODO

## Group 1 — Database & Schema

- [x] PostgreSQL 16 running in Docker
- [x] Initial migration: `projects`, `distros`, `releases`, `packages`, `aliases`, `project_package_map` tables
- [x] `pg_trgm` extension + GIN index on `package_name`
- [x] `distros` seeded (6 distros, incl. install command templates)
- [x] Seed `releases` table (bookworm, jammy, noble, trixie, alpine edge, etc.)
- [ ] Materialized view `project_best_install` (one row per project + distro family)

## Group 2 — Data Ingestion

- [x] Debian ingestion (`debian bookworm` — 63k packages)
- [x] Ubuntu ingestion (`ubuntu noble` — 6k packages)
- [ ] Ingest more Ubuntu releases (jammy LTS)
- [ ] Alpine ingestion
- [ ] Arch Linux ingestion
- [ ] Fedora ingestion
- [ ] openSUSE ingestion
- [ ] Scheduled/automated ingest (GH Actions cron or worker)
- [ ] Mark stale packages after re-ingest (`last_seen` cutoff)

## Group 3 — API

- [x] `/healthz`
- [x] `/api/v1/distros`
- [x] `/api/v1/packages?distro=&release=&q=`
- [x] `/api/v1/packages/{distro}/{release}/{name}`
- [x] `/api/v1/search?q=&distro=` (ILIKE on `package_name`)
- [x] `/api/v1/install/{name}?distro=auto`
- [x] `/api/v1/projects/{name}`
- [x] Upgrade search to `pg_trgm` similarity (GIN index already exists)
- [ ] Search across `projects.normalized_name` + `aliases` + `description`
- [ ] `Cache-Control` headers on `/search`, `/projects/*`, `/install/*`
- [ ] Rate limiting (Phase 2 — Redis)

## Group 4 — Frontend (Astro)

- [x] Home page — centered search box + feature tiles
- [x] Search results page (`/search?q=`) — **client-side rendering** (Astro static mode
  doesn't expose query params via `Astro.url` in the dev container; JS reads
  `window.location.search` and fetches the API directly from the browser)
- [x] Search form has a Submit button
- [x] Package page (`/p/{name}`) — install tabs + versions table
- [x] Copy button on install command blocks
- [x] `/distros` page — grid of distros + releases + package counts (client-side)
- [ ] Distro badge styling on search results
- [ ] Sidebar filters (distro, release) on search results page
- [ ] Trending / recently updated packages on home page
- [ ] `/about` page
- [ ] `/api` docs page
- [x] Fix SSR in Docker: added `API_INTERNAL_BASE=http://api:8000/api/v1` to
  docker-compose web env; `api.ts` now prefers it over `PUBLIC_API_BASE` so
  SSR fetches (e.g. `index.astro` hero stats) resolve via Docker service name

<!-- REMINDER FOR AI AGENTS (CLAUDE / COPILOT):
     After any non-trivial change, update this file and run:
       git add -A && git commit -m "feat/fix: <short description>"
     Keep commits small and descriptive. -->

## Reminders (for AI agents & contributors)

- **After every meaningful change**: update this file, then `git add -A && git commit -m "…"`
- **Commit often** — one logical change per commit, conventional-commit style
- **Before starting a task**: mark the relevant TODO(s) in-progress here

## Group 5 — Projects & Mapping (Phase 2)

- [ ] Populate `projects` table (canonical names)
- [ ] `aliases` table data
- [ ] Mapping pipeline: `packages → projects` (rules + upstream URL matching)
- [ ] `project_package_map` populated with confidence scores
- [ ] Update `/search` to return project-level results with `best_install` field

## Group 7 — CLI (Phase 3)

- [x] Create `cli/` Go module (`gitea.eduluma.org/eduluma/lps/cli`)
- [x] `lps search`, `lps install`, `lps info` commands (thin HTTP client)
- [x] `/etc/os-release` auto-detect for distro/release
- [x] `~/.config/lps/config.toml` read/write (`lps config set / show / path`)
- [x] `.goreleaser.yaml` config (Gitea target, all 5 platforms)
- [ ] CI release pipeline — push tag → goreleaser → Gitea releases
- [ ] `install.sh` one-liner script (detects OS/arch, downloads from Gitea, verifies checksum)
- [ ] Homebrew tap (`eduluma/lps-tap`)
- [ ] AUR `lps-bin` PKGBUILD

- [x] Docker Compose dev stack (db, migrate, seed, api, web, ingest)
- [x] Taskfile (dev, test, migrate, seed, ingest, fmt, lint)
- [x] Hot reload working (uvicorn `--reload-dir app`)
- [x] `.github/copilot-instructions.md` — agent workflow rules, stack, traffic flow
- [ ] Deploy API + DB to Fly.io (or Railway/Hetzner)
- [ ] Deploy Astro frontend (Cloudflare Pages or same host)
- [ ] Cloudflare CDN in front of API
- [ ] Astro static pre-render of `/p/{name}` pages at build time
- [ ] Redis cache + rate limiting (Phase 2)
- [ ] Meilisearch (Phase 2, for typo-tolerance)
