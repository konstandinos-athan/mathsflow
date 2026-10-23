CREATE TRIGGER question_versions_no_update BEFORE UPDATE ON question_versions BEGIN SELECT RAISE(ABORT,'Question revisions are immutable'); END;
CREATE TRIGGER question_versions_no_delete BEFORE DELETE ON question_versions BEGIN SELECT RAISE(ABORT,'Question revisions are immutable'); END;
CREATE TRIGGER theory_versions_no_update BEFORE UPDATE ON theory_versions BEGIN SELECT RAISE(ABORT,'Theory revisions are immutable'); END;
CREATE TRIGGER theory_versions_no_delete BEFORE DELETE ON theory_versions BEGIN SELECT RAISE(ABORT,'Theory revisions are immutable'); END;
CREATE TRIGGER current_question_owner_insert BEFORE INSERT ON current_questions
WHEN NOT EXISTS(SELECT 1 FROM question_versions WHERE id=NEW.version_id AND question_id=NEW.question_id)
BEGIN SELECT RAISE(ABORT,'Revision belongs to a different question'); END;
CREATE TRIGGER current_question_owner_update BEFORE UPDATE ON current_questions
WHEN NOT EXISTS(SELECT 1 FROM question_versions WHERE id=NEW.version_id AND question_id=NEW.question_id)
BEGIN SELECT RAISE(ABORT,'Revision belongs to a different question'); END;
CREATE TRIGGER current_theory_owner_insert BEFORE INSERT ON current_theory
WHEN NOT EXISTS(SELECT 1 FROM theory_versions WHERE id=NEW.version_id AND unit_id=NEW.unit_id)
BEGIN SELECT RAISE(ABORT,'Revision belongs to a different unit'); END;
CREATE TRIGGER current_theory_owner_update BEFORE UPDATE ON current_theory
WHEN NOT EXISTS(SELECT 1 FROM theory_versions WHERE id=NEW.version_id AND unit_id=NEW.unit_id)
BEGIN SELECT RAISE(ABORT,'Revision belongs to a different unit'); END;
CREATE TRIGGER attempt_question_unit BEFORE INSERT ON attempt_questions
WHEN NOT EXISTS(SELECT 1 FROM question_versions v JOIN questions q ON q.id=v.question_id JOIN quiz_attempts a ON a.id=NEW.attempt_id WHERE v.id=NEW.version_id AND q.unit_id=a.unit_id)
BEGIN SELECT RAISE(ABORT,'Attempt question belongs to a different unit'); END;
CREATE TRIGGER attempt_questions_no_update BEFORE UPDATE ON attempt_questions BEGIN SELECT RAISE(ABORT,'Attempt question order is immutable'); END;
CREATE TRIGGER completed_attempt_no_update BEFORE UPDATE ON quiz_attempts WHEN OLD.submitted_at IS NOT NULL BEGIN SELECT RAISE(ABORT,'Completed attempt is immutable'); END;
CREATE TRIGGER responses_no_update BEFORE UPDATE ON responses BEGIN SELECT RAISE(ABORT,'Submitted responses are immutable'); END;
