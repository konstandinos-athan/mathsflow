CREATE TABLE schools (id TEXT PRIMARY KEY, title TEXT NOT NULL);
CREATE TABLE grades (id TEXT PRIMARY KEY, school_id TEXT NOT NULL REFERENCES schools(id), title TEXT NOT NULL);
CREATE TABLE curriculum_sources (id TEXT PRIMARY KEY, payload TEXT NOT NULL CHECK(json_valid(payload)));
CREATE TABLE books (id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES curriculum_sources(id), title TEXT NOT NULL);
CREATE TABLE courses (
 id TEXT PRIMARY KEY, course_key TEXT NOT NULL UNIQUE, grade_id TEXT NOT NULL REFERENCES grades(id),
 subject_key TEXT NOT NULL, title TEXT NOT NULL, school_year TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload)), UNIQUE(grade_id, subject_key, school_year)
);
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
 blocks TEXT NOT NULL CHECK(json_valid(blocks)), created_at REAL NOT NULL, UNIQUE(unit_id,content_hash)
);
CREATE TABLE current_theory (unit_id TEXT PRIMARY KEY REFERENCES units(id), version_id TEXT NOT NULL REFERENCES theory_versions(id));
CREATE TABLE questions (id TEXT PRIMARY KEY, unit_id TEXT NOT NULL REFERENCES units(id), display_order INTEGER NOT NULL CHECK(display_order>0));
CREATE INDEX questions_unit_order ON questions(unit_id,display_order);
CREATE TABLE question_versions (
 id TEXT PRIMARY KEY, question_id TEXT NOT NULL REFERENCES questions(id), content_hash TEXT NOT NULL,
 payload TEXT NOT NULL CHECK(json_valid(payload)), difficulty TEXT NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
 created_at REAL NOT NULL, UNIQUE(question_id,content_hash)
);
CREATE TABLE current_questions (question_id TEXT PRIMARY KEY REFERENCES questions(id), version_id TEXT NOT NULL REFERENCES question_versions(id));
CREATE TABLE users (
 id TEXT PRIMARY KEY, email TEXT NOT NULL COLLATE NOCASE UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('student','admin')), created_at REAL NOT NULL
);
CREATE TABLE quiz_attempts (
 id TEXT PRIMARY KEY, unit_id TEXT NOT NULL REFERENCES units(id), user_id TEXT REFERENCES users(id),
 difficulty TEXT NOT NULL CHECK(difficulty IN ('all','easy','medium','hard')),
 started_at REAL NOT NULL, submitted_at REAL, score INTEGER,
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
 mastery REAL NOT NULL DEFAULT 0 CHECK(mastery BETWEEN 0 AND 1), updated_at REAL NOT NULL,
 PRIMARY KEY(user_id,unit_id)
);
CREATE TABLE reward_ledger (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), event_id TEXT NOT NULL,
 reward_type TEXT NOT NULL, xp INTEGER NOT NULL CHECK(xp>=0), created_at REAL NOT NULL,
 UNIQUE(user_id,event_id,reward_type)
);
CREATE TABLE import_runs (name TEXT PRIMARY KEY, content_hash TEXT NOT NULL, imported_at REAL NOT NULL, summary TEXT NOT NULL CHECK(json_valid(summary)));
