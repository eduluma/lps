-- rollback 0003
ALTER TABLE suggestions DROP COLUMN IF EXISTS user_id;
DROP TABLE IF EXISTS users;
