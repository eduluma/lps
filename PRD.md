# LPS — Linux Package Search

> A brew.sh-style search experience for Linux packages across distributions.
> One query → one working install command, with details a click away.

---

## 1. Goal

Build a unified search system across Linux distributions (Debian, Ubuntu, Alpine, Arch, Fedora, openSUSE, etc.) that:

- Returns a **single working install command** for the 90% case
- Hides distro complexity by default, exposes it on demand
- Provides a **brew.sh-like web page** per package (clean, link-rich, scannable)
- Exposes a **public JSON API** usable from CLI tools (`curl`, `lps search ...`)
- Supports multi-distro comparison and basic analytics
- Scales to ~1M package records

---

## 2. Core UX (the 90% case)

Web flow:

1. Visit `lps.dev` → single search box (Homebrew-style)
2. Type `lazygit` → results list with project name, short description, distro badges
3. Click result → **package page** with:
   - Name, description, homepage, source
   - **One install command** (auto-detected distro, with tabs for others)
   - Latest versions per distro/release
   - Links: upstream, distro package pages, source
   - Copy button on the command

CLI flow:

```bash
curl -s https://lps.dev/api/v1/search?q=lazygit | jq
curl -s https://lps.dev/api/v1/install/lazygit?distro=alpine
# => apk add lazygit
```

---

## 3. Tech Stack

**v1 pick: Astro + FastAPI (asyncpg) + PostgreSQL + Cloudflare.**

| Layer     | Choice                                                         | Why                                                                                    |
| --------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| DB        | **PostgreSQL 16**                                              | Relational + JSONB + FTS + `pg_trgm`, mature                                           |
| Search    | **Postgres FTS + `pg_trgm`** (MVP) → **Meilisearch** (Phase 2) | Skip extra infra at start; upgrade when typo-tolerance matters                         |
| API       | **FastAPI + asyncpg** on **uvicorn + uvloop**                  | Async all the way to Postgres; auto OpenAPI → typed TS client; multi-worker behind CDN |
| Ingestion | **Python workers** + cron / GH Actions                         | Best parser library coverage (`python-debian`, `rpm`, etc.); shares lang with API      |
| Cache     | **Cloudflare** (edge) + **Redis** (Phase 2)                    | CDN absorbs 95%+ of traffic; Redis for rate limiting + hot keys                        |
| Frontend  | **Astro + Tailwind**                                           | Static-first, fastest TTFB, SEO-friendly — matches the brew.sh feel                    |
| Hosting   | Fly.io / Railway / Hetzner                                     | Cheap, simple                                                                          |
| CDN       | Cloudflare                                                     | Cache API + static frontend                                                            |

### Performance strategy

- Async stack end-to-end: `uvicorn[standard]` (uvloop + httptools) + `asyncpg` connection pool.
- `Cache-Control: public, s-maxage=300, stale-while-revalidate=86400` on `/search`, `/projects/*`, `/install/*`.
- Materialized view `project_best_install` (one row per project + distro family) refreshed after each ingestion run → API does an indexed lookup, no JOIN at request time.
- Static `/p/{project}` pages pre-rendered by Astro on build/ingestion; revalidated on demand.
- Run API as N worker processes (`--workers $(nproc)`); single Postgres reader pool per worker.

### Frontend choice

Astro is the default because most of LPS is essentially **static content with a search box** — exactly its sweet spot. Use **Next.js (App Router)** instead only if/when we need heavy dynamic UI (auth, user submissions, dashboards). Both consume the same FastAPI JSON API, so this is a swap, not a rewrite.

### Alternatives considered

| Stack                               | Verdict                                                                                                                                |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **Next.js + NestJS + Postgres**     | NestJS is over-architected for a thin REST-over-Postgres API; ingestion still wants Python. Pick **Hono** over Nest if going TS-first. |
| **Next.js + Java (Spring/Quarkus)** | Highest sustained throughput, but slowest iteration and overkill for v1 — CDN absorbs the load anyway.                                 |
| **Astro/Next + Go (chi)**           | Best perf/$ at scale; reserved as the **escape hatch** if FastAPI ever bottlenecks. Keep Python ingestion.                             |

Migration path if we outgrow v1:
1. Add Meilisearch.
2. Add Redis cache + rate limiting.
3. Port hot API endpoints to Go (chi + pgx); keep Python ingestion and the same Postgres.

---

## 4. Architecture

```text
        ┌────────────────────┐
        │  Distro Mirrors    │
        │ (apt/apk/pacman/…) │
        └─────────┬──────────┘
                  │ scheduled fetch
        ┌─────────▼──────────┐
        │ Ingestion Workers  │  (Python, one parser per distro)
        └─────────┬──────────┘
                  │ upsert
        ┌─────────▼──────────┐         ┌──────────────┐
        │   PostgreSQL       │ ───────▶│ Meilisearch  │  (Phase 2)
        │ projects/packages  │  index  │   search     │
        └─────────┬──────────┘         └──────┬───────┘
                  │                           │
                  └────────────┬──────────────┘
                               │
                      ┌────────▼─────────┐
                      │   FastAPI        │  /api/v1/...
                      └────────┬─────────┘
                               │
                      ┌────────▼─────────┐
                      │ Astro Frontend   │  lps.dev
                      └──────────────────┘
```

---

## 5. Design Principles

1. **Separate identity from distribution.** `Project` = what the user wants; `Package` = how a distro provides it. Names are not reliable cross-distro identity.
2. **Show one command, hide complexity.** Collapse versions, distros, arches by default.
3. **UX first, analytics second.** Clean search/install flow; analytics easy via SQL.
4. **Start simple, add structure gradually.** Begin with `packages`; add `projects` + mapping over time.
5. **Read-heavy, cache-friendly.** Static-ish package pages; aggressive CDN caching.

---

## 6. Database Schema

### `projects` — canonical software identity

```sql
CREATE TABLE projects (
  id SERIAL PRIMARY KEY,
  canonical_name TEXT NOT NULL,        -- "lazygit"
  normalized_name TEXT NOT NULL,       -- "lazygit"
  description TEXT,
  homepage_url TEXT,
  source_url TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_projects_normalized_name ON projects(normalized_name);
```

### `packages` — distro-specific data (core table)

```sql
CREATE TABLE packages (
  id SERIAL PRIMARY KEY,
  project_id INT REFERENCES projects(id),

  distro TEXT NOT NULL,                -- debian, ubuntu, alpine, arch, fedora
  release TEXT NOT NULL,               -- bookworm, jammy, edge, rolling
  repo TEXT,                           -- main, universe, community, extra
  arch TEXT DEFAULT 'amd64',

  package_name TEXT NOT NULL,
  version TEXT NOT NULL,
  description TEXT,

  homepage_url TEXT,
  maintainer TEXT,
  download_url TEXT,                   -- distro package page
  size_bytes BIGINT,

  first_seen TIMESTAMP,
  last_seen TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_packages_unique
  ON packages(distro, release, repo, package_name, arch);
CREATE INDEX idx_packages_project ON packages(project_id);
```

### `aliases` — search enhancement

```sql
CREATE TABLE aliases (
  id SERIAL PRIMARY KEY,
  project_id INT REFERENCES projects(id),
  alias TEXT NOT NULL,                 -- "git ui", "lazy git"
  normalized_alias TEXT NOT NULL
);
CREATE INDEX idx_aliases_normalized ON aliases(normalized_alias);
```

### `distros` — metadata + install templates

```sql
CREATE TABLE distros (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE,                    -- debian, ubuntu, alpine, arch, fedora
  family TEXT,                         -- debian, arch, rpm, alpine
  package_manager TEXT,                -- apt, apk, pacman, dnf, zypper
  install_command_template TEXT,       -- "sudo apt install {pkg}"
  search_command_template TEXT,        -- "apt search {q}"
  package_url_template TEXT            -- "https://packages.debian.org/{release}/{pkg}"
);
```

### `releases` — version context

```sql
CREATE TABLE releases (
  id SERIAL PRIMARY KEY,
  distro_id INT REFERENCES distros(id),
  name TEXT,                           -- bookworm, jammy
  is_lts BOOLEAN DEFAULT FALSE,
  is_stable BOOLEAN DEFAULT TRUE,
  release_date DATE,
  eol_date DATE
);
```

### `project_package_map` — optional advanced mapping

```sql
CREATE TABLE project_package_map (
  id SERIAL PRIMARY KEY,
  project_id INT REFERENCES projects(id),
  package_id INT REFERENCES packages(id),
  confidence_score FLOAT DEFAULT 1.0,
  is_primary BOOLEAN DEFAULT TRUE
);
```

---

## 7. Data Ingestion

**Sources:**

| Distro   | Source                                                        | Format     |
| -------- | ------------------------------------------------------------- | ---------- |
| Debian   | `deb.debian.org/debian/dists/{release}/.../Packages.xz`       | RFC822-ish |
| Ubuntu   | `archive.ubuntu.com/ubuntu/dists/{release}/.../Packages.xz`   | same       |
| Alpine   | `dl-cdn.alpinelinux.org/alpine/{release}/.../APKINDEX.tar.gz` | tar        |
| Arch     | `archlinux.org/packages/search/json/?...`                     | JSON       |
| Fedora   | DNF repodata (`repomd.xml` + `primary.xml.gz`)                | XML        |
| openSUSE | OBS / repodata                                                | XML        |

**Pipeline:**

1. Daily cron (GH Actions or worker) per `(distro, release, repo, arch)`.
2. Download index, parse → normalized rows.
3. Idempotent upsert into `packages` (key: distro, release, repo, package_name, arch).
4. Update `last_seen`; mark stale rows for review.
5. Re-index changed rows into search engine.
6. (Phase 2) Run mapper to link `package → project`.

---

## 8. Search Flow

1. Normalize query (lowercase, strip punctuation).
2. Search `projects.normalized_name` + `aliases.normalized_alias` + `description`.
3. Resolve `project_id` → fetch related `packages` (latest version per distro/release).
4. Rank and return.
5. Fallback: if no project match, search `packages.package_name` directly.

**Default ranking for the "best install" pick:**

1. Debian stable
2. Ubuntu LTS (latest)
3. Fedora stable
4. Alpine stable
5. Arch (rolling)

User's detected distro (UA hint or explicit selector) overrides default.

---

## 9. API (v1)

Base: `https://lps.dev/api/v1`

| Method | Path                                             | Description                                     |
| ------ | ------------------------------------------------ | ----------------------------------------------- |
| GET    | `/search?q=lazygit&distro=debian`                | Full-text search; returns project hits          |
| GET    | `/projects/{name}`                               | Project detail + all packages grouped by distro |
| GET    | `/packages?distro=debian&release=bookworm&q=git` | Raw package search                              |
| GET    | `/packages/{distro}/{release}/{name}`            | Specific package detail                         |
| GET    | `/distros`                                       | List of supported distros + templates           |
| GET    | `/install/{name}?distro=auto`                    | Returns best install command (text or JSON)     |
| GET    | `/healthz`                                       | Health check                                    |

**Example — `GET /search?q=lazygit`:**

```json
{
  "query": "lazygit",
  "results": [
    {
      "project": "lazygit",
      "description": "Simple terminal UI for git commands",
      "homepage": "https://github.com/jesseduffield/lazygit",
      "best_install": {
        "distro": "debian",
        "release": "bookworm",
        "command": "sudo apt install lazygit"
      },
      "available_in": ["debian", "ubuntu", "alpine", "arch", "fedora"],
      "url": "https://lps.dev/p/lazygit"
    }
  ]
}
```

**CLI usage:**

```bash
curl -s "https://lps.dev/api/v1/install/lazygit?distro=alpine"
# => apk add lazygit
```

---

## 10. Web Pages (brew.sh-style)

### Home (`/`)

- Centered title + tagline + giant search input
- Below: trending packages, recently updated, short "How it works"
- Footer: GitHub, API docs, supported distros

### Search results (`/search?q=...`)

- Project cards: name, description, distro badges
- Sidebar filters: distro, release

### Package page (`/p/{project}`)

Like a `formulae.brew.sh` page:

- **Header:** name, one-line description, homepage / source links
- **Install block:** big code box with copy button, distro tabs (Debian | Ubuntu | Alpine | Arch | Fedora)
- **Versions table:** distro · release · version · last seen
- **Metadata:** maintainer, license (if available), size
- **Links:** upstream, distro package pages, "Report incorrect mapping"

### `/distros`, `/about`, `/api` (docs)

Static-rendered via Astro; revalidated after ingestion runs.

---

## 11. Install Command Templates

Stored in `distros.install_command_template`:

```text
debian   → sudo apt install {pkg}
ubuntu   → sudo apt install {pkg}
alpine   → apk add {pkg}
arch     → sudo pacman -S {pkg}
fedora   → sudo dnf install {pkg}
opensuse → sudo zypper install {pkg}
```

---

## 12. Analytics (sample queries)

```sql
-- Packages per distro
SELECT distro, COUNT(*) FROM packages GROUP BY distro;

-- Unique project coverage per distro
SELECT distro, COUNT(DISTINCT project_id) FROM packages GROUP BY distro;

-- Projects available everywhere
SELECT p.canonical_name
FROM projects p
JOIN packages pk ON pk.project_id = p.id
GROUP BY p.canonical_name
HAVING COUNT(DISTINCT pk.distro) >= 5;
```

---

## 13. Known Challenges

1. **Package name mismatch** (`python3-requests` vs `python-requests`).
2. **Missing packages across distros.**
3. **Mapping packages → projects** (hardest; solve with rules + manual overrides + upstream URL matching).
4. **Version normalization** across distro schemes.
5. **Index freshness** vs ingestion cost.

---

## 14. Roadmap

### Phase 1 — MVP (search works end-to-end)

- Postgres + `packages` + `distros` + `releases` tables
- Ingestion: Debian stable + Ubuntu LTS + Alpine stable
- FastAPI: `/search`, `/packages/...`, `/install/...`, `/distros`
- Astro frontend: home, search, basic package page
- Postgres FTS (no Meilisearch yet)
- Deploy to Fly.io behind Cloudflare

### Phase 2 — Projects & UX polish

- Add `projects` + `aliases` + `project_package_map`
- Mapping pipeline (rules + upstream URL match)
- Add Arch + Fedora ingestion
- Switch to Meilisearch
- Brew-style package page with tabs + copy button
- Redis cache + rate limiting

### Phase 3 — Scale & community

- Ranking refinements, distro auto-detect
- "Report mapping" feedback flow
- Analytics dashboard
- `lps` CLI (Go single binary — see §17)
- openSUSE, Void, NixOS (with caveats)

---

## 17. CLI (`lps`) — Go single binary

### Why Go

A Go binary is statically compiled and ships with zero runtime dependencies.
One `go build` per target → works on every Linux distro, macOS, and WSL without
installing Python, a package manager, or anything else.

Cross-compilation targets (from a single Mac or CI runner):

| Target         | Env vars                    |
| -------------- | --------------------------- |
| Linux x86-64   | `GOOS=linux GOARCH=amd64`   |
| Linux arm64    | `GOOS=linux GOARCH=arm64`   |
| macOS arm64    | `GOOS=darwin GOARCH=arm64`  |
| macOS x86-64   | `GOOS=darwin GOARCH=amd64`  |
| Windows x86-64 | `GOOS=windows GOARCH=amd64` |

### Distribution channels

Releases are published to **`gitea.eduluma.org/eduluma/lps`** (self-hosted Gitea)
via [goreleaser](https://goreleaser.com) on every version tag.
The `/cli` web page fetches the latest release from Gitea's REST API at render time
(`GET /api/v1/repos/eduluma/lps/releases/latest`) and renders live download buttons —
no manual link updates needed when a new version ships.

| Channel               | How                                                                     |
| --------------------- | ----------------------------------------------------------------------- |
| **Gitea Releases**    | Primary. Binaries + SHA-256 checksums uploaded by goreleaser on tag push |
| **`lps.eduluma.org/cli`** | Download page — SSR fetches Gitea API, renders platform buttons     |
| **`install.sh`**      | `curl -fsSL https://lps.eduluma.org/install.sh \| sh` — detects OS/arch, downloads from Gitea, verifies checksum |
| **Homebrew tap**      | `eduluma/lps-tap` formula pointing at the Gitea release asset           |
| **AUR (`lps-bin`)**   | PKGBUILD downloads the Gitea pre-built binary                           |
| **Alpine apk**        | Submit to Alpine `testing` once traction is established                 |
| **`.deb` / `.rpm`**   | Build packages in CI (goreleaser); host on a self-managed apt/yum repo  |

### Commands

```bash
lps search lazygit               # search packages, respects saved distro pref
lps install lazygit              # print the install command for your distro
lps info lazygit                 # full project detail + all distro versions
lps config set distro debian     # save preference
lps config set release bookworm  # save preference
lps config show                  # print current config
```

`lps install lazygit` on Alpine prints `apk add lazygit` and exits — the user
can pipe or copy it. On distros with a saved preference it skips auto-detection.

### Config file

Stored at `$XDG_CONFIG_HOME/lps/config.toml` (falls back to `~/.config/lps/config.toml`).
Created on first `lps config set …` run. Never created implicitly.

```toml
# ~/.config/lps/config.toml

[user]
distro   = "debian"       # overrides auto-detect from /etc/os-release
release  = "bookworm"     # overrides auto-detect
token    = ""             # future: API key for rate-limit bypass / private data

[api]
base_url = "https://lps.eduluma.org/api/v1"   # override for self-hosted instances

[output]
format = "text"           # text | json
color  = true
```

**Auto-detection fallback** (when `distro` is unset):
1. Read `/etc/os-release` → `ID` + `VERSION_CODENAME`.
2. Normalize to known distro slug (debian, ubuntu, alpine, arch, fedora, opensuse).
3. If unrecognised, fall back to the API's default ranking (Debian stable).

### Repository location

`cli/` in the monorepo (Phase 3). Separate `go.mod`. CI publishes via
[goreleaser](https://goreleaser.com) on tag push.

---

## 15. Repository Layout (proposed)

```text
lps/
├── api/                  # FastAPI app
│   ├── app/
│   ├── tests/
│   └── pyproject.toml
├── ingest/               # Per-distro parsers + scheduler
│   ├── debian/
│   ├── alpine/
│   ├── arch/
│   └── common/
├── cli/                  # Go binary (Phase 3)
│   ├── cmd/lps/main.go
│   ├── internal/
│   │   ├── api/          # HTTP client for lps API
│   │   ├── config/       # TOML config read/write
│   │   └── distro/       # /etc/os-release auto-detect
│   └── go.mod
├── web/                  # Astro frontend
│   ├── src/
│   └── package.json
├── db/
│   ├── migrations/       # Alembic
│   └── seed/
├── infra/                # Docker, Fly/Railway configs
├── docs/
├── PRD.md
├── NAMING.md
└── README.md
```

---

## 16. Core Insight

> Store **raw truth** in `packages`, store **meaning** in `projects`.

This enables a clean Homebrew-like UX, scalable architecture, and honest multi-distro support.
Here’s a clean, copy-pasteable Markdown summary of everything we designed—focused, practical, and ready to use:

# Linux Multi-Distro Package Search System — Design Summary

## 🎯 Goal

Build a unified search system across Linux distributions (Debian, Ubuntu, Alpine, Arch, etc.) that:

- Gives users a **single working install command (90% use case)**
- Hides distro complexity by default
- Supports **multi-distro comparison and analytics**
- Scales to ~1M package records
- Can evolve into a **Homebrew-like UX layer**

---

## 🧠 Key Design Principles

### 1. Separate Identity from Distribution

- **Project** = what user wants (e.g. lazygit)
- **Package** = how distro provides it

👉 Package names are NOT reliable identity across distros

---

### 2. Show One Command, Hide Complexity

- Default:

## sudo apt install lazygit

- Collapse:
- versions
- distros
- architectures

---

### 3. Optimize for UX First, Analytics Second

- Clean search + install flow
- Analytics still easy via SQL

---

### 4. Start Simple → Add Structure Gradually

- Begin with `packages`
- Add `projects` + mapping over time

---

## 🧱 Database Schema

---

### 📦 `projects` — Canonical Software Identity

```sql
CREATE TABLE projects (
id SERIAL PRIMARY KEY,
canonical_name TEXT NOT NULL,        -- "lazygit"
normalized_name TEXT NOT NULL,       -- "lazygit"
description TEXT,
homepage_url TEXT,
source_url TEXT,
created_at TIMESTAMP DEFAULT NOW(),
updated_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_projects_normalized_name 
ON projects(normalized_name);

## 📦 packages — Distro-Specific Data (Core Table)

CREATE TABLE packages (
  id SERIAL PRIMARY KEY,
  project_id INT REFERENCES projects(id),

  distro TEXT NOT NULL,                -- debian, ubuntu, alpine, arch
  release TEXT NOT NULL,               -- bookworm, jammy, edge
  repo TEXT,                           -- main, universe, community
  arch TEXT DEFAULT 'amd64',

  package_name TEXT NOT NULL,
  version TEXT NOT NULL,
  description TEXT,

  homepage_url TEXT,
  maintainer TEXT,

  first_seen TIMESTAMP,
  last_seen TIMESTAMP,

  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_packages_unique 
ON packages(distro, release, repo, package_name, arch);

## 🔍 aliases — Search Enhancement

CREATE TABLE aliases (
  id SERIAL PRIMARY KEY,
  project_id INT REFERENCES projects(id),
  alias TEXT NOT NULL,                 -- "git ui", "lazy git"
  normalized_alias TEXT NOT NULL
);

CREATE INDEX idx_aliases_normalized 
ON aliases(normalized_alias);

## 🔗 project_package_map (Optional Advanced Mapping)

CREATE TABLE project_package_map (
  id SERIAL PRIMARY KEY,
  project_id INT REFERENCES projects(id),
  package_id INT REFERENCES packages(id),
  confidence_score FLOAT DEFAULT 1.0,
  is_primary BOOLEAN DEFAULT TRUE
);

## 🧭 distros — Metadata

CREATE TABLE distros (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE,                    -- debian, ubuntu, alpine
  family TEXT,                         -- debian, arch, etc.
  package_manager TEXT,                -- apt, apk, pacman
  install_command_template TEXT        -- "sudo apt install {pkg}"
);

## 🗂 releases — Version Context

CREATE TABLE releases (
  id SERIAL PRIMARY KEY,
  distro_id INT REFERENCES distros(id),
  name TEXT,                           -- bookworm, jammy
  is_lts BOOLEAN DEFAULT FALSE,
  is_stable BOOLEAN DEFAULT TRUE,
  release_date DATE,
  eol_date DATE
);


## 🔄 Data Ingestion Strategy

Sources
- Debian/Ubuntu → Packages.xz
- Alpine → APKINDEX
- Arch → pacman DB
Process
- Fetch metadata daily (cron job)
- Parse into normalized rows
- Insert/update packages
- Optionally map to projects

## 🔍 Search Flow

1. User query → normalize text
2. Search:
- projects.normalized_name
- aliases.normalized_alias
3. Resolve project_id
4. Fetch related packages
5. Rank + display

## 🎯 Ranking Strategy
Default priority:
Debian Stable
Ubuntu LTS
Alpine Stable
Rolling distros (Arch, etc.)

## 🧾 Install Command Generation
Use template from distros:
Examples:
```bash
# Debian / Ubuntu
sudo apt install lazygit

# Alpine
apk add lazygit

# Arch
pacman -S lazygit
```

## 📊 Analytics (Simple Queries)

Package count per distro

```sql
SELECT distro, COUNT(*) 
FROM packages 
GROUP BY distro;
```

## Unique project coverage

```sql
SELECT distro, COUNT(DISTINCT project_id) 
FROM packages 
GROUP BY distro;
```

## ⚠️ Known Challenges

1. Package Name Mismatch
python3-requests vs python-requests
2. Missing Packages Across Distros
Not all tools exist everywhere
3. Mapping Packages → Projects
Hardest problem
Solve incrementally

## 🚀 MVP Plan

### Phase 1

packages table
basic search
direct install command

### Phase 2

add projects
alias support
grouping

### Phase 3

ranking
UI polish (Homebrew-style)
analytics dashboard

## 💡 Core Insight

Store raw truth in packages, store meaning in projects

This enables:

- clean UX
- scalable architecture
- multi-distro support

## 🏁 Outcome

A system that:

- Feels like Homebrew
- Works across all Linux distros
- Hides complexity
- Scales cleanly
