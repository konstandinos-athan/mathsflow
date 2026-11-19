-- PostgreSQL baseline equivalent to SQLite migrations 001-005.
CREATE FUNCTION json_valid(value TEXT) RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN PERFORM value::json; RETURN TRUE;
EXCEPTION WHEN invalid_text_representation THEN RETURN FALSE; END;
$$;
CREATE FUNCTION json_extract(value TEXT, path TEXT) RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
SELECT value::jsonb #>> string_to_array(substr(path,3),'.');
$$;
CREATE FUNCTION json_each(document TEXT, path TEXT) RETURNS TABLE(value TEXT) LANGUAGE sql IMMUTABLE AS $$
SELECT jsonb_array_elements_text(document::jsonb #> string_to_array(substr(path,3),'.'));
$$;
CREATE TABLE schools (id TEXT PRIMARY KEY, title TEXT NOT NULL, rowid BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE);

CREATE TABLE grades (id TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES schools(id), title TEXT NOT NULL, rowid BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE);

CREATE TABLE curriculum_sources (id TEXT PRIMARY KEY, payload TEXT NOT NULL CHECK(json_valid(payload)));

CREATE TABLE books (id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES curriculum_sources(id), title TEXT NOT NULL);

CREATE TABLE courses (
 id TEXT PRIMARY KEY, course_key TEXT NOT NULL UNIQUE, grade_id TEXT NOT NULL REFERENCES grades(id),
 subject_key TEXT NOT NULL, title TEXT NOT NULL, school_year TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload)), UNIQUE(grade_id, subject_key, school_year)
, rowid BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE);

CREATE TABLE chapters (id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id), book_id TEXT NOT NULL REFERENCES books(id), title TEXT NOT NULL);

CREATE TABLE units (
 id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id), chapter_id TEXT NOT NULL REFERENCES chapters(id),
 reference TEXT NOT NULL, title TEXT NOT NULL, display_order INTEGER NOT NULL CHECK(display_order>0),
 payload TEXT NOT NULL CHECK(json_valid(payload))
);

CREATE INDEX units_course_order ON units(course_id, display_order);

CREATE TABLE objectives (id TEXT PRIMARY KEY, unit_id TEXT NOT NULL REFERENCES units(id), payload TEXT NOT NULL CHECK(json_valid(payload)));

CREATE TABLE skills (id TEXT PRIMARY KEY, title TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)));

CREATE TABLE skill_edges (skill_id TEXT NOT NULL REFERENCES skills(id), prerequisite_id TEXT NOT NULL REFERENCES skills(id), PRIMARY KEY(skill_id, prerequisite_id), CHECK(skill_id != prerequisite_id));

CREATE TABLE unit_prerequisites (unit_id TEXT NOT NULL REFERENCES units(id), skill_id TEXT NOT NULL REFERENCES skills(id), PRIMARY KEY(unit_id,skill_id));

CREATE TABLE unit_sources (unit_id TEXT NOT NULL REFERENCES units(id), ordinal INTEGER NOT NULL, source_id TEXT NOT NULL REFERENCES curriculum_sources(id), payload TEXT NOT NULL CHECK(json_valid(payload)), PRIMARY KEY(unit_id,ordinal));

CREATE TABLE legacy_routes (
 school_key TEXT NOT NULL, grade_key TEXT NOT NULL, subject_key TEXT NOT NULL,
 lesson_id INTEGER NOT NULL CHECK(lesson_id>0), unit_id TEXT NOT NULL UNIQUE REFERENCES units(id),
 PRIMARY KEY(school_key,grade_key,subject_key,lesson_id)
);

CREATE TABLE theory_versions (
 id TEXT PRIMARY KEY, unit_id TEXT NOT NULL REFERENCES units(id), content_hash TEXT NOT NULL,
 blocks TEXT NOT NULL CHECK(json_valid(blocks)), created_at DOUBLE PRECISION NOT NULL, UNIQUE(unit_id,content_hash)
);

CREATE TABLE current_theory (unit_id TEXT PRIMARY KEY REFERENCES units(id), version_id TEXT NOT NULL REFERENCES theory_versions(id));

CREATE TABLE questions (id TEXT PRIMARY KEY, unit_id TEXT NOT NULL REFERENCES units(id), display_order INTEGER NOT NULL CHECK(display_order>0));

CREATE INDEX questions_unit_order ON questions(unit_id,display_order);

CREATE TABLE question_versions (
 id TEXT PRIMARY KEY, question_id TEXT NOT NULL REFERENCES questions(id), content_hash TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload)), difficulty TEXT NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
 created_at DOUBLE PRECISION NOT NULL, UNIQUE(question_id,content_hash)
);

CREATE TABLE current_questions (question_id TEXT PRIMARY KEY REFERENCES questions(id), version_id TEXT NOT NULL REFERENCES question_versions(id));

CREATE TABLE users (
 id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('student','admin')), created_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE quiz_attempts (
 id TEXT PRIMARY KEY, unit_id TEXT NOT NULL REFERENCES units(id), user_id TEXT REFERENCES users(id),
 difficulty TEXT NOT NULL CHECK(difficulty IN ('all','easy','medium','hard')),
 started_at DOUBLE PRECISION NOT NULL, submitted_at DOUBLE PRECISION, score INTEGER,
 total INTEGER NOT NULL CHECK(total>0),
 CHECK((submitted_at IS NULL AND score IS NULL) OR (submitted_at IS NOT NULL AND score BETWEEN 0 AND total))
);

CREATE TABLE attempt_questions (
 attempt_id TEXT NOT NULL REFERENCES quiz_attempts(id), position INTEGER NOT NULL CHECK(position>=0),
 version_id TEXT NOT NULL REFERENCES question_versions(id), choices TEXT NOT NULL CHECK(json_valid(choices)),
 PRIMARY KEY(attempt_id,position), UNIQUE(attempt_id,version_id)
);

CREATE TABLE responses (
 attempt_id TEXT NOT NULL, position INTEGER NOT NULL, selected TEXT, correct INTEGER NOT NULL CHECK(correct IN (0,1)),
 PRIMARY KEY(attempt_id,position), FOREIGN KEY(attempt_id,position) REFERENCES attempt_questions(attempt_id,position)
);

CREATE TABLE user_progress (
 user_id TEXT NOT NULL REFERENCES users(id), unit_id TEXT NOT NULL REFERENCES units(id),
 mastery DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK(mastery BETWEEN 0 AND 1), updated_at DOUBLE PRECISION NOT NULL,
 PRIMARY KEY(user_id,unit_id)
);

CREATE TABLE reward_ledger (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), event_id TEXT NOT NULL,
 reward_type TEXT NOT NULL, xp INTEGER NOT NULL CHECK(xp>=0), created_at DOUBLE PRECISION NOT NULL,
 UNIQUE(user_id,event_id,reward_type)
);

CREATE TABLE import_runs (name TEXT PRIMARY KEY, content_hash TEXT NOT NULL, imported_at DOUBLE PRECISION NOT NULL, summary TEXT NOT NULL CHECK(json_valid(summary)));

ALTER TABLE quiz_attempts ADD COLUMN mode TEXT NOT NULL DEFAULT 'practice' CHECK(mode IN ('practice','exam'));

ALTER TABLE users RENAME COLUMN email TO username;

CREATE TABLE account_security (
 user_id TEXT PRIMARY KEY REFERENCES users(id), recovery_hash TEXT NOT NULL,
 privacy_version TEXT NOT NULL, accepted_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE auth_sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX auth_sessions_user ON auth_sessions(user_id);

CREATE TABLE auth_limits (key TEXT PRIMARY KEY, hits INTEGER NOT NULL, expires_at DOUBLE PRECISION NOT NULL);

CREATE TABLE account_deletions (user_id TEXT PRIMARY KEY);

CREATE UNIQUE INDEX users_username_casefold ON users(lower(username));

CREATE FUNCTION question_versions_no_update_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Question revisions are immutable' USING ERRCODE='23514'; RETURN NEW; END;
$$;
CREATE TRIGGER question_versions_no_update BEFORE UPDATE ON question_versions FOR EACH ROW EXECUTE FUNCTION question_versions_no_update_fn();

CREATE FUNCTION question_versions_no_delete_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Question revisions are immutable' USING ERRCODE='23514'; RETURN OLD; END;
$$;
CREATE TRIGGER question_versions_no_delete BEFORE DELETE ON question_versions FOR EACH ROW EXECUTE FUNCTION question_versions_no_delete_fn();

CREATE FUNCTION theory_versions_no_update_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Theory revisions are immutable' USING ERRCODE='23514'; RETURN NEW; END;
$$;
CREATE TRIGGER theory_versions_no_update BEFORE UPDATE ON theory_versions FOR EACH ROW EXECUTE FUNCTION theory_versions_no_update_fn();

CREATE FUNCTION theory_versions_no_delete_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Theory revisions are immutable' USING ERRCODE='23514'; RETURN OLD; END;
$$;
CREATE TRIGGER theory_versions_no_delete BEFORE DELETE ON theory_versions FOR EACH ROW EXECUTE FUNCTION theory_versions_no_delete_fn();

CREATE FUNCTION current_question_owner_insert_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN IF NOT EXISTS(SELECT 1 FROM question_versions WHERE id=NEW.version_id AND question_id=NEW.question_id) THEN RAISE EXCEPTION 'Revision belongs to a different question' USING ERRCODE='23514'; END IF; RETURN NEW; END;
$$;
CREATE TRIGGER current_question_owner_insert BEFORE INSERT ON current_questions FOR EACH ROW EXECUTE FUNCTION current_question_owner_insert_fn();

CREATE FUNCTION current_question_owner_update_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN IF NOT EXISTS(SELECT 1 FROM question_versions WHERE id=NEW.version_id AND question_id=NEW.question_id) THEN RAISE EXCEPTION 'Revision belongs to a different question' USING ERRCODE='23514'; END IF; RETURN NEW; END;
$$;
CREATE TRIGGER current_question_owner_update BEFORE UPDATE ON current_questions FOR EACH ROW EXECUTE FUNCTION current_question_owner_update_fn();

CREATE FUNCTION current_theory_owner_insert_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN IF NOT EXISTS(SELECT 1 FROM theory_versions WHERE id=NEW.version_id AND unit_id=NEW.unit_id) THEN RAISE EXCEPTION 'Revision belongs to a different unit' USING ERRCODE='23514'; END IF; RETURN NEW; END;
$$;
CREATE TRIGGER current_theory_owner_insert BEFORE INSERT ON current_theory FOR EACH ROW EXECUTE FUNCTION current_theory_owner_insert_fn();

CREATE FUNCTION current_theory_owner_update_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN IF NOT EXISTS(SELECT 1 FROM theory_versions WHERE id=NEW.version_id AND unit_id=NEW.unit_id) THEN RAISE EXCEPTION 'Revision belongs to a different unit' USING ERRCODE='23514'; END IF; RETURN NEW; END;
$$;
CREATE TRIGGER current_theory_owner_update BEFORE UPDATE ON current_theory FOR EACH ROW EXECUTE FUNCTION current_theory_owner_update_fn();

CREATE FUNCTION attempt_question_unit_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN IF NOT EXISTS(SELECT 1 FROM question_versions v JOIN questions q ON q.id=v.question_id JOIN quiz_attempts a ON a.id=NEW.attempt_id WHERE v.id=NEW.version_id AND q.unit_id=a.unit_id) THEN RAISE EXCEPTION 'Attempt question belongs to a different unit' USING ERRCODE='23514'; END IF; RETURN NEW; END;
$$;
CREATE TRIGGER attempt_question_unit BEFORE INSERT ON attempt_questions FOR EACH ROW EXECUTE FUNCTION attempt_question_unit_fn();

CREATE FUNCTION attempt_questions_no_update_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Attempt question order is immutable' USING ERRCODE='23514'; RETURN NEW; END;
$$;
CREATE TRIGGER attempt_questions_no_update BEFORE UPDATE ON attempt_questions FOR EACH ROW EXECUTE FUNCTION attempt_questions_no_update_fn();

CREATE FUNCTION completed_attempt_no_update_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN IF OLD.submitted_at IS NOT NULL THEN RAISE EXCEPTION 'Completed attempt is immutable' USING ERRCODE='23514'; END IF; RETURN NEW; END;
$$;
CREATE TRIGGER completed_attempt_no_update BEFORE UPDATE ON quiz_attempts FOR EACH ROW EXECUTE FUNCTION completed_attempt_no_update_fn();

CREATE FUNCTION responses_no_update_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Submitted responses are immutable' USING ERRCODE='23514'; RETURN NEW; END;
$$;
CREATE TRIGGER responses_no_update BEFORE UPDATE ON responses FOR EACH ROW EXECUTE FUNCTION responses_no_update_fn();

CREATE FUNCTION unit_chapter_owner_insert_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN IF NOT EXISTS(SELECT 1 FROM chapters WHERE id=NEW.chapter_id AND course_id=NEW.course_id) THEN RAISE EXCEPTION 'Chapter belongs to another course' USING ERRCODE='23514'; END IF; RETURN NEW; END;
$$;
CREATE TRIGGER unit_chapter_owner_insert BEFORE INSERT ON units FOR EACH ROW EXECUTE FUNCTION unit_chapter_owner_insert_fn();

CREATE FUNCTION unit_chapter_owner_update_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN IF NOT EXISTS(SELECT 1 FROM chapters WHERE id=NEW.chapter_id AND course_id=NEW.course_id) THEN RAISE EXCEPTION 'Chapter belongs to another course' USING ERRCODE='23514'; END IF; RETURN NEW; END;
$$;
CREATE TRIGGER unit_chapter_owner_update BEFORE UPDATE ON units FOR EACH ROW EXECUTE FUNCTION unit_chapter_owner_update_fn();

CREATE FUNCTION responses_no_delete_after_submit_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN IF EXISTS(SELECT 1 FROM quiz_attempts a WHERE a.id=OLD.attempt_id AND a.submitted_at IS NOT NULL
 AND NOT EXISTS(SELECT 1 FROM account_deletions d WHERE d.user_id=a.user_id)) THEN RAISE EXCEPTION 'Completed responses are immutable' USING ERRCODE='23514'; END IF; RETURN OLD; END;
$$;
CREATE TRIGGER responses_no_delete_after_submit BEFORE DELETE ON responses FOR EACH ROW EXECUTE FUNCTION responses_no_delete_after_submit_fn();

CREATE FUNCTION attempt_questions_no_delete_after_submit_fn() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN IF EXISTS(SELECT 1 FROM quiz_attempts a WHERE a.id=OLD.attempt_id AND a.submitted_at IS NOT NULL
 AND NOT EXISTS(SELECT 1 FROM account_deletions d WHERE d.user_id=a.user_id)) THEN RAISE EXCEPTION 'Completed attempt questions are immutable' USING ERRCODE='23514'; END IF; RETURN OLD; END;
$$;
CREATE TRIGGER attempt_questions_no_delete_after_submit BEFORE DELETE ON attempt_questions FOR EACH ROW EXECUTE FUNCTION attempt_questions_no_delete_after_submit_fn();
