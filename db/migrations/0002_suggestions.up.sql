-- 0002 crowd-sourced package suggestions
-- Users can submit package suggestions; other users upvote them.
-- Anti-spam: daily IP rate-limit enforced in the API layer.
-- Anti-duplicate: unique constraint on (package_name, distro, release, status=pending).

CREATE TABLE IF NOT EXISTS suggestions (
  id           SERIAL PRIMARY KEY,
  package_name TEXT        NOT NULL,
  distro       TEXT        NOT NULL,
  release      TEXT        NOT NULL,
  install_cmd  TEXT        NOT NULL,
  description  TEXT        NOT NULL,
  homepage_url TEXT,
  submitter_ip TEXT        NOT NULL,
  -- pending = awaiting review  |  approved = merged into packages  |  rejected = spam/invalid
  status       TEXT        NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'approved', 'rejected')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fast lookup for the browse page (vote-sorted pending suggestions)
CREATE INDEX IF NOT EXISTS idx_suggestions_status
  ON suggestions(status, created_at DESC);

-- Fast rate-limit check
CREATE INDEX IF NOT EXISTS idx_suggestions_submitter
  ON suggestions(submitter_ip, created_at DESC);

-- Prevent exact duplicates while a suggestion is still pending
CREATE UNIQUE INDEX IF NOT EXISTS idx_suggestions_no_dup
  ON suggestions(lower(package_name), distro, lower(release))
  WHERE status = 'pending';

-- Each IP can only vote once per suggestion (primary key = natural dedup)
CREATE TABLE IF NOT EXISTS suggestion_votes (
  suggestion_id INT         NOT NULL REFERENCES suggestions(id) ON DELETE CASCADE,
  voter_ip      TEXT        NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (suggestion_id, voter_ip)
);
