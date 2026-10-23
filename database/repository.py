"""Runtime queries. Does not import the original content Python modules."""
import json
import random
import time
import uuid
from . import encode


class Repository:
    def __init__(self, connection):
        self.db = connection

    def navigation(self):
        result = {}
        for row in self.db.execute('SELECT * FROM schools ORDER BY rowid'):
            result[row['id']] = {'name': row['title'], 'classes': {}}
        for row in self.db.execute('SELECT * FROM grades ORDER BY rowid'):
            result[row['school_id']]['classes'][row['id']] = {'name': row['title'], 'subjects': {}}
        for row in self.db.execute('SELECT c.*,g.school_id FROM courses c JOIN grades g ON g.id=c.grade_id ORDER BY c.rowid'):
            result[row['school_id']]['classes'][row['grade_id']]['subjects'][row['subject_key']] = {
                'name': row['title'], 'course_id': row['id'], 'lessons': self.lessons(row['id'])}
        return result

    def lessons(self, course_id):
        return [dict(r) for r in self.db.execute('''SELECT u.id,u.reference,u.title,u.display_order,
            json_extract(u.payload,'$.teaching_scope') AS teaching_scope,
            EXISTS(SELECT 1 FROM current_theory t WHERE t.unit_id=u.id) AS has_theory,
            EXISTS(SELECT 1 FROM questions q JOIN current_questions cq ON cq.question_id=q.id WHERE q.unit_id=u.id) AS has_quiz
            FROM units u WHERE course_id=? ORDER BY display_order,u.id''', (course_id,))]

    def unit(self, unit_id):
        row = self.db.execute('''SELECT u.*, c.subject_key,c.title AS subject_name,c.grade_id AS class_key,
            g.school_id AS school_key,g.title AS class_name,s.title AS school_name
            FROM units u JOIN courses c ON c.id=u.course_id JOIN grades g ON g.id=c.grade_id
            JOIN schools s ON s.id=g.school_id WHERE u.id=?''', (unit_id,)).fetchone()
        return dict(row) if row else None

    def legacy_unit(self, school, grade, subject, lesson_id):
        row = self.db.execute('SELECT unit_id FROM legacy_routes WHERE school_key=? AND grade_key=? AND subject_key=? AND lesson_id=?', (school, grade, subject, lesson_id)).fetchone()
        return self.unit(row[0]) if row else None

    def theory(self, unit_id):
        row = self.db.execute('SELECT v.blocks FROM current_theory c JOIN theory_versions v ON v.id=c.version_id WHERE c.unit_id=?', (unit_id,)).fetchone()
        return json.loads(row[0]) if row else []

    def questions(self, unit_id, difficulty='all'):
        rows = self.db.execute('''SELECT v.id AS version_id,v.payload FROM questions q
            JOIN current_questions c ON c.question_id=q.id JOIN question_versions v ON v.id=c.version_id
            WHERE q.unit_id=? AND (?='all' OR v.difficulty=?) ORDER BY q.display_order,q.id''', (unit_id, difficulty, difficulty))
        return [{**json.loads(r['payload']), 'version_id': r['version_id']} for r in rows]

    def start_attempt(self, unit_id, difficulty):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            questions = self.questions(unit_id, difficulty)
            if not questions:
                self.db.rollback()
                return None
            random.shuffle(questions)
            attempt_id = str(uuid.uuid4())
            self.db.execute('INSERT INTO quiz_attempts(id,unit_id,difficulty,started_at,total) VALUES (?,?,?,?,?)', (attempt_id, unit_id, difficulty, time.time(), len(questions)))
            for i, question in enumerate(questions):
                choices = question['choices'][:]
                random.shuffle(choices)
                self.db.execute('INSERT INTO attempt_questions VALUES (?,?,?,?)', (attempt_id, i, question['version_id'], encode(choices)))
            self.db.commit()
            return self.attempt(attempt_id)
        except Exception:
            self.db.rollback()
            raise

    def attempt(self, attempt_id):
        row = self.db.execute('SELECT * FROM quiz_attempts WHERE id=?', (attempt_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result['questions'] = []
        for question in self.db.execute('''SELECT a.position,a.choices,v.payload,v.id AS version_id FROM attempt_questions a
            JOIN question_versions v ON v.id=a.version_id WHERE a.attempt_id=? ORDER BY a.position''', (attempt_id,)):
            result['questions'].append({**json.loads(question['payload']), 'choices': json.loads(question['choices']), 'version_id': question['version_id']})
        result['user_answers'] = {str(r['position']): r['selected'] for r in self.db.execute('SELECT position,selected FROM responses WHERE attempt_id=?', (attempt_id,))}
        return result

    def submit_attempt(self, attempt_id, unit_id, difficulty, answers):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            attempt = self.attempt(attempt_id)
            if not attempt or attempt['unit_id'] != unit_id or attempt['difficulty'] != difficulty:
                raise ValueError('Invalid quiz attempt')
            if time.time() - attempt['started_at'] > 7200:
                raise ValueError('Quiz attempt expired')
            # A duplicate request returns the original result, never replaces it.
            if attempt['submitted_at'] is not None:
                self.db.rollback()
                return attempt
            score = 0
            for i, question in enumerate(attempt['questions']):
                selected = answers.get(f'question_{i}')
                if selected is not None and selected not in question['choices']:
                    raise ValueError('Answer is not one of the displayed choices')
                correct = selected == question['answer']
                score += int(correct)
                self.db.execute('INSERT INTO responses VALUES (?,?,?,?)', (attempt_id, i, selected, int(correct)))
            self.db.execute('UPDATE quiz_attempts SET submitted_at=?,score=? WHERE id=?', (time.time(), score, attempt_id))
            self.db.commit()
            return self.attempt(attempt_id)
        except Exception:
            self.db.rollback()
            raise
