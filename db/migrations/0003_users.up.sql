-- 0003 registered users + API tokens
-- Users register once, receive a stable bearer token (lps_...).
-- Anonymous suggestion submissions remain allowed; token holders get
-- higher rate limits and attribution on their suggestions.

CREATE TABLE IF NOT EXISTS users (
  id           SERIAL PRIMARY KEY,
  email        TEXT        UNIQUE NOT NULL,
  display_name TEXT        NOT NULL,
  -- individual = person, org = company/team (reserved for future tiers)
  account_type TEXT        NOT NULL DEFAULT 'individual'
               CHECK (account_type IN ('individual', 'org')),
  token        TEXT        UNIQUE NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Token lookup is hot-path on every authenticated request
CREATE INDEX IF NOT EXISTS idx_users_token ON users(token);

-- Attribute suggestions to registered users (nullable — anon OK)
ALTER TABLE suggestions
  ADD COLUMN IF NOT EXISTS user_id INT REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_suggestions_user ON suggestions(user_id);
