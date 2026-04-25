-- 0004 rollback
DROP INDEX IF EXISTS idx_ingest_jobs_distro_release;
DROP INDEX IF EXISTS idx_ingest_jobs_active;
DROP TABLE IF EXISTS ingest_jobs;
DROP TABLE IF EXISTS distro_requests;
DROP TABLE IF EXISTS distro_sources;
ALTER TABLE users DROP COLUMN IF EXISTS plan_expires_at;
ALTER TABLE users DROP COLUMN IF EXISTS plan;
ALTER TABLE users DROP COLUMN IF EXISTS role;
