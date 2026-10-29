ALTER TABLE quiz_attempts ADD COLUMN mode TEXT NOT NULL DEFAULT 'practice' CHECK(mode IN ('practice','exam'));
