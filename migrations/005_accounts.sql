ALTER TABLE users RENAME COLUMN email TO username;
CREATE TABLE account_security (
 user_id TEXT PRIMARY KEY REFERENCES users(id), recovery_hash TEXT NOT NULL,
 privacy_version TEXT NOT NULL, accepted_at REAL NOT NULL
);
CREATE TABLE auth_sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires_at REAL NOT NULL
);
CREATE INDEX auth_sessions_user ON auth_sessions(user_id);
CREATE TABLE auth_limits (key TEXT PRIMARY KEY, hits INTEGER NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE account_deletions (user_id TEXT PRIMARY KEY);
DROP TRIGGER responses_no_delete_after_submit;
DROP TRIGGER attempt_questions_no_delete_after_submit;
CREATE TRIGGER responses_no_delete_after_submit BEFORE DELETE ON responses
WHEN EXISTS(SELECT 1 FROM quiz_attempts a WHERE a.id=OLD.attempt_id AND a.submitted_at IS NOT NULL
 AND NOT EXISTS(SELECT 1 FROM account_deletions d WHERE d.user_id=a.user_id))
BEGIN SELECT RAISE(ABORT,'Completed responses are immutable'); END;
CREATE TRIGGER attempt_questions_no_delete_after_submit BEFORE DELETE ON attempt_questions
WHEN EXISTS(SELECT 1 FROM quiz_attempts a WHERE a.id=OLD.attempt_id AND a.submitted_at IS NOT NULL
 AND NOT EXISTS(SELECT 1 FROM account_deletions d WHERE d.user_id=a.user_id))
BEGIN SELECT RAISE(ABORT,'Completed attempt questions are immutable'); END;
