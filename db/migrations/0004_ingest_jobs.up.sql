-- 0004 distro onboarding, ingest job queue, user roles & plan

-- ── users: role + monetisation-ready plan columns ──────────────────────────
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'viewer'
    CHECK (role IN ('viewer', 'maintainer', 'admin'));

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free'
    CHECK (plan IN ('free', 'pro', 'enterprise'));

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS plan_expires_at TIMESTAMPTZ;

-- ── distro_sources: config-driven ingest registry ──────────────────────────
-- One row per (distro, release) that the worker knows how to pull.
-- format values:
--   apt    → debian/ubuntu style APT Packages.gz
--   rpm    → RPM repodata primary.xml (Fedora, openSUSE)
--   apk    → Alpine apk APKINDEX
--   aur    → Arch AUR / pacman sync DB
--   custom → handled by a dedicated Python module; base_url is informational
CREATE TABLE IF NOT EXISTS distro_sources (
  id           SERIAL PRIMARY KEY,
  distro       TEXT        NOT NULL,
  release      TEXT        NOT NULL,
  format       TEXT        NOT NULL
               CHECK (format IN ('apt', 'rpm', 'apk', 'aur', 'custom')),
  base_url     TEXT        NOT NULL,
  -- format-specific knobs, e.g. {"component":"main","arch":"amd64"} for apt
  extra_config JSONB       NOT NULL DEFAULT '{}',
  enabled      BOOLEAN     NOT NULL DEFAULT TRUE,
  added_by     INT         REFERENCES users(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (distro, release)
);

-- ── distro_requests: community intake ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS distro_requests (
  id           SERIAL PRIMARY KEY,
  distro_name  TEXT        NOT NULL,
  release_name TEXT,
  format       TEXT        CHECK (format IN ('apt', 'rpm', 'apk', 'aur', 'other')),
  base_url     TEXT,
  description  TEXT,
  contact_info TEXT,
  status       TEXT        NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending', 'approved', 'rejected', 'implemented')),
  user_id      INT         REFERENCES users(id) ON DELETE SET NULL,
  reviewed_by  INT         REFERENCES users(id) ON DELETE SET NULL,
  -- set to the resulting distro_sources row when implemented
  source_id    INT         REFERENCES distro_sources(id) ON DELETE SET NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── ingest_jobs: job queue + permanent audit trail ─────────────────────────
CREATE TABLE IF NOT EXISTS ingest_jobs (
  id                 SERIAL PRIMARY KEY,
  distro             TEXT        NOT NULL,
  release            TEXT        NOT NULL,
  -- NULL means triggered via CLI / scheduled, not from distro_sources
  source_id          INT         REFERENCES distro_sources(id) ON DELETE SET NULL,
  status             TEXT        NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'running', 'done', 'failed')),
  triggered_by       INT         REFERENCES users(id) ON DELETE SET NULL,
  packages_upserted  INT,
  error_message      TEXT,
  started_at         TIMESTAMPTZ,
  finished_at        TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Only one active (pending OR running) job allowed per distro/release at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_ingest_jobs_active
  ON ingest_jobs (distro, release)
  WHERE status IN ('pending', 'running');

-- Fast lookup: recent jobs for a distro/release
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_distro_release
  ON ingest_jobs (distro, release, created_at DESC);
