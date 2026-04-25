-- 0001 initial schema
-- See PRD.md §6

CREATE TABLE IF NOT EXISTS projects (
  id SERIAL PRIMARY KEY,
  canonical_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  description TEXT,
  homepage_url TEXT,
  source_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_normalized_name
  ON projects(normalized_name);

CREATE TABLE IF NOT EXISTS distros (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  family TEXT,
  package_manager TEXT,
  install_command_template TEXT,
  search_command_template TEXT,
  package_url_template TEXT
);

CREATE TABLE IF NOT EXISTS releases (
  id SERIAL PRIMARY KEY,
  distro_id INT REFERENCES distros(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  is_lts BOOLEAN DEFAULT FALSE,
  is_stable BOOLEAN DEFAULT TRUE,
  release_date DATE,
  eol_date DATE,
  UNIQUE (distro_id, name)
);

CREATE TABLE IF NOT EXISTS packages (
  id SERIAL PRIMARY KEY,
  project_id INT REFERENCES projects(id) ON DELETE SET NULL,

  distro TEXT NOT NULL,
  release TEXT NOT NULL,
  repo TEXT,
  arch TEXT DEFAULT 'amd64',

  package_name TEXT NOT NULL,
  version TEXT NOT NULL,
  description TEXT,

  homepage_url TEXT,
  maintainer TEXT,
  download_url TEXT,
  size_bytes BIGINT,

  first_seen TIMESTAMPTZ,
  last_seen TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_packages_unique
  ON packages(distro, release, repo, package_name, arch);
CREATE INDEX IF NOT EXISTS idx_packages_project ON packages(project_id);
CREATE INDEX IF NOT EXISTS idx_packages_name ON packages(package_name);

CREATE TABLE IF NOT EXISTS aliases (
  id SERIAL PRIMARY KEY,
  project_id INT REFERENCES projects(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  normalized_alias TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aliases_normalized ON aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS project_package_map (
  id SERIAL PRIMARY KEY,
  project_id INT REFERENCES projects(id) ON DELETE CASCADE,
  package_id INT REFERENCES packages(id) ON DELETE CASCADE,
  confidence_score FLOAT DEFAULT 1.0,
  is_primary BOOLEAN DEFAULT TRUE,
  UNIQUE (project_id, package_id)
);

-- Trigram index for fuzzy package_name search (Phase 1 search)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_packages_name_trgm
  ON packages USING gin (package_name gin_trgm_ops);
