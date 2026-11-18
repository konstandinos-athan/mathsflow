import json
import uuid
from contextlib import closing
from database import connect, encode
from database.progress import student_progress
from tests.support import DatabaseCase
from tests import test_auth


class ProgressTests(DatabaseCase):
    password = test_auth.AuthTests.password
    csrf = test_auth.AuthTests.csrf
    register = test_auth.AuthTests.register

    def setUp(self):
        super().setUp()
        self.app.config['AUTH_ENABLED'] = True
        self.register()
        self.owner = self.db.execute('SELECT id FROM users').fetchone()[0]
        self.unit = self.repo.legacy_unit('gel', 'a-gel', 'algebra', 1)['id']
        self.objective = self.db.execute('SELECT id FROM objectives WHERE unit_id=? ORDER BY id', (self.unit,)).fetchone()[0]
        # Preserve legacy versions; bind fresh versions to a known objective.
        for row in self.db.execute('''SELECT v.* FROM question_versions v JOIN current_questions c
                ON c.version_id=v.id JOIN questions q ON q.id=v.question_id WHERE q.unit_id=?''', (self.unit,)).fetchall():
            payload = json.loads(row['payload'])
            payload['objective_ids'] = [self.objective]
            version = str(uuid.uuid4())
            self.db.execute('INSERT INTO question_versions VALUES (?,?,?,?,?,?)',
                            (version, row['question_id'], version, encode(payload), row['difficulty'], row['created_at']))
            self.db.execute('UPDATE current_questions SET version_id=? WHERE question_id=?', (version, row['question_id']))
        self.db.commit()

    def submit(self, correct=False, owner=None):
        attempt = self.repo.start_attempt(self.unit, 'all', user_id=owner or self.owner)
        answers = {f'question_{i}': q['answer'] for i, q in enumerate(attempt['questions'])} if correct else {}
        return self.repo.submit_attempt(attempt['id'], self.unit, 'all', answers)

    def test_empty_incomplete_and_anonymous_do_not_count(self):
        self.repo.start_attempt(self.unit, 'all', user_id=self.owner)
        anon = self.repo.start_attempt(self.unit, 'all')
        self.repo.submit_attempt(anon['id'], self.unit, 'all', {})
        data = student_progress(self.db, self.owner)
        self.assertEqual((data['count'], data['covered'], data['objectives']), (0, 0, []))
        page = self.client.get('/account/progress')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Η αρχή γίνεται'.encode(), page.data)
        self.assertEqual(page.headers['Cache-Control'], 'no-store')

    def test_latest_distinct_questions_blanks_and_duplicate_submission(self):
        first = self.submit()
        data = student_progress(self.db, self.owner)
        target = next(o for o in data['objectives'] if o['id'] == self.objective)
        self.assertEqual((target['samples'], target['unanswered'], target['wrong']), (5, 5, 0))
        self.assertEqual(len(data['recommendations']), 1)
        self.repo.submit_attempt(first['id'], self.unit, 'all', {})
        self.assertEqual(student_progress(self.db, self.owner)['count'], 1)
        self.submit(True)
        data = student_progress(self.db, self.owner)
        target = next(o for o in data['objectives'] if o['id'] == self.objective)
        self.assertEqual((target['samples'], target['correct']), (5, 5))
        self.assertEqual(target['status'], 'Καλή πρόσφατη επίδοση')
        self.assertEqual(data['recommendations'], [])
        self.assertTrue(any(o['samples'] == 0 for o in data['objectives']))
        with closing(connect(self.path)) as reopened:
            self.assertEqual(student_progress(reopened, self.owner), data)

    def test_owner_only_results_and_history(self):
        attempt = self.submit(True)
        url = '/account/attempt/' + attempt['id']
        self.assertEqual(self.client.get(url).status_code, 200)
        other = self.app.test_client()
        self.assertEqual(other.get(url).status_code, 401)
        self.register(other, 'student_2')
        self.assertEqual(other.get(url).status_code, 404)
        self.assertIn('Η αρχή γίνεται'.encode(), other.get('/account/progress').data)
        pending = self.repo.start_attempt(self.unit, 'all', user_id=self.owner)
        self.assertEqual(self.client.get('/account/attempt/' + pending['id']).status_code, 404)
        self.app.config['AUTH_ENABLED'] = False
        self.assertEqual(self.client.get('/account/progress').status_code, 404)

    def test_history_pagination_and_invalid_pages(self):
        for _ in range(21):
            self.submit()
        first = student_progress(self.db, self.owner)
        second = student_progress(self.db, self.owner, 2)
        self.assertEqual((first['count'], len(first['history']), len(second['history'])), (21, 20, 1))
        self.assertFalse({a['id'] for a in first['history']} & {a['id'] for a in second['history']})
        self.assertEqual(self.client.get('/account/progress?page=2').status_code, 200)
        for value in ('0', '-1', 'x', '1&page=2', '9999999999', ''):
            self.assertEqual(self.client.get('/account/progress?page=' + value).status_code, 400)

    def test_deletion_removes_derived_progress(self):
        self.submit()
        token = self.csrf(self.client, '/account/delete')
        response = self.client.post('/account/delete', data=dict(csrf=token, current_password=self.password, confirmation='ΔΙΑΓΡΑΦΗ'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(student_progress(self.db, self.owner)['count'], 0)
        self.assertEqual(student_progress(self.db, self.owner)['objectives'], [])

    def test_few_samples_do_not_claim_good_performance(self):
        ids = [row[0] for row in self.db.execute('SELECT id FROM questions WHERE unit_id=? ORDER BY id', (self.unit,))]
        for question_id in ids[2:]:
            self.db.execute('DELETE FROM current_questions WHERE question_id=?', (question_id,))
        self.db.commit()
        self.submit(True)
        target = next(o for o in student_progress(self.db, self.owner)['objectives'] if o['id'] == self.objective)
        self.assertEqual((target['samples'], target['percent'], target['status']), (2, 100, 'Λίγα στοιχεία'))

    def test_wrong_answers_and_future_content_preserve_history(self):
        attempt = self.repo.start_attempt(self.unit, 'all', user_id=self.owner)
        self.repo.submit_attempt(attempt['id'], self.unit, 'all', {
            f'question_{i}': next(c for c in q['choices'] if c != q['answer'])
            for i, q in enumerate(attempt['questions'])})
        before = student_progress(self.db, self.owner)
        target = next(o for o in before['objectives'] if o['id'] == self.objective)
        self.assertEqual((target['wrong'], target['unanswered'], target['correct']), (5, 0, 0))
        # Changing the live bank cannot rewrite the saved evidence.
        self.db.execute('DELETE FROM current_questions WHERE question_id IN (SELECT id FROM questions WHERE unit_id=?)', (self.unit,))
        self.db.commit()
        self.assertEqual(student_progress(self.db, self.owner), before)
        self.assertEqual(self.client.get('/account/attempt/' + attempt['id']).status_code, 200)
