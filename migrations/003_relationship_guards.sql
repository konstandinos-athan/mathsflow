CREATE TRIGGER unit_chapter_owner_insert BEFORE INSERT ON units
WHEN NOT EXISTS(SELECT 1 FROM chapters WHERE id=NEW.chapter_id AND course_id=NEW.course_id)
BEGIN SELECT RAISE(ABORT,'Chapter belongs to another course'); END;
CREATE TRIGGER unit_chapter_owner_update BEFORE UPDATE ON units
WHEN NOT EXISTS(SELECT 1 FROM chapters WHERE id=NEW.chapter_id AND course_id=NEW.course_id)
BEGIN SELECT RAISE(ABORT,'Chapter belongs to another course'); END;
CREATE TRIGGER attempt_questions_no_delete_after_submit BEFORE DELETE ON attempt_questions
WHEN EXISTS(SELECT 1 FROM quiz_attempts WHERE id=OLD.attempt_id AND submitted_at IS NOT NULL)
BEGIN SELECT RAISE(ABORT,'Completed attempt questions are immutable'); END;
CREATE TRIGGER responses_no_delete_after_submit BEFORE DELETE ON responses
WHEN EXISTS(SELECT 1 FROM quiz_attempts WHERE id=OLD.attempt_id AND submitted_at IS NOT NULL)
BEGIN SELECT RAISE(ABORT,'Completed responses are immutable'); END;
