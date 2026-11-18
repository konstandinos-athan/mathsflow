import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch
from database import connect, copy_database
from database.repository import Repository
from database.rewards import rewards_summary, award_attempt
from tests.support import DatabaseCase
from tests import test_auth


class RewardTests(DatabaseCase):
    password = test_auth.AuthTests.password
    csrf = test_auth.AuthTests.csrf
    register = test_auth.AuthTests.register

    def setUp(self):
        super().setUp()
        self.app.config['AUTH_ENABLED'] = True
        self.register()
        self.owner = self.db.execute('SELECT id FROM users').fetchone()[0]
        self.unit = self.repo.legacy_unit('gel', 'a-gel', 'algebra', 1)['id']

    def begin(self, mode='practice', owner=None):
        return self.repo.start_attempt(self.unit, 'all', mode, user_id=owner or self.owner)

    @staticmethod
    def answers(attempt):
        return {f'question_{i}': q['answer'] for i, q in enumerate(attempt['questions'])}

    def finish(self, attempt, answers=None, repo=None):
        return (repo or self.repo).submit_attempt(attempt['id'], self.unit, 'all',
            self.answers(attempt) if answers is None else answers, attempt['mode'])

    def summary(self):
        return rewards_summary(self.db, self.owner)

    def test_new_student_then_level_and_badges(self):
        empty = self.summary()
        self.assertEqual((empty['xp'], empty['level'], empty['next_xp']), (0, 1, 100))
        self.assertFalse(any(b['earned'] for b in empty['badges']))
        attempt = self.begin()
        self.finish(attempt)
        reward = self.summary()
        self.assertEqual(reward['xp'], 10 * attempt['total'])
        self.assertEqual(reward['level'], 1+reward['xp']//100)
        self.assertTrue(reward['badges'][0]['earned'])
        page = self.client.get('/account/progress')
        self.assertEqual(page.status_code, 200)
        self.assertIn(f"{reward['xp']} XP".encode(), page.data)

    def test_duplicate_and_new_exam_do_not_farm_xp(self):
        attempt = self.begin()
        self.finish(attempt)
        expected = self.summary()
        self.finish(attempt, {})
        self.finish(self.begin('exam'))
        self.finish(self.begin(), {})
        self.assertEqual(self.summary(), expected)

    def test_wrong_blank_anonymous_pending_and_client_xp(self):
        pending = self.begin()
        with self.assertRaises(ValueError):
            self.finish(pending, {'xp': '999999'})
        self.assertEqual(self.summary()['xp'], 0)
        wrong = {f'question_{i}': next(c for c in q['choices'] if c != q['answer'])
                 for i, q in enumerate(pending['questions']) if i % 2 == 0}
        self.finish(pending, wrong)
        anonymous = self.repo.start_attempt(self.unit, 'all')
        self.finish(anonymous)
        self.assertEqual(self.summary()['xp'], 0)
        self.finish(self.begin())
        self.assertEqual(self.summary()['xp'], pending['total']*10)

    def test_award_failure_rolls_back_grade_and_answers(self):
        attempt = self.begin()
        def fail_after_insert(db, attempt_id):
            award_attempt(db, attempt_id)
            raise RuntimeError('failure after award')
        with patch('database.rewards.award_attempt', side_effect=fail_after_insert):
            with self.assertRaises(RuntimeError):
                self.finish(attempt)
        self.assertIsNone(self.repo.attempt(attempt['id'])['score'])
        self.assertEqual(self.repo.attempt(attempt['id'])['user_answers'], {})
        self.assertEqual(self.summary()['xp'], 0)
        self.finish(attempt)
        self.assertEqual(self.summary()['xp'], attempt['total']*10)

    def test_old_attempt_reads_and_reposts_do_not_backfill(self):
        attempt = self.begin()
        with patch('database.rewards.award_attempt'):
            self.finish(attempt)
        self.assertEqual(self.client.get('/account/attempt/' + attempt['id']).status_code, 200)
        self.assertEqual(self.client.get('/account/progress').status_code, 200)
        self.finish(attempt)
        self.assertEqual(self.summary()['xp'], 0)

    def concurrent(self, attempts):
        barrier = threading.Barrier(2)
        def submit(attempt):
            with closing(connect(self.path)) as db:
                barrier.wait(timeout=10)
                return self.finish(attempt, repo=Repository(db))['score']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, attempts))
        self.assertEqual(results, [a['total'] for a in attempts])
        self.assertEqual(self.summary()['xp'], attempts[0]['total']*10)

    def test_concurrent_same_attempt_awarded_once(self):
        attempt = self.begin()
        self.concurrent([attempt, attempt])

    def test_concurrent_different_attempts_same_questions_awarded_once(self):
        self.concurrent([self.begin(), self.begin('exam')])

    def test_new_content_versions_do_not_repeat_rewards(self):
        self.finish(self.begin())
        expected = self.summary()
        for row in self.db.execute('''SELECT v.* FROM question_versions v JOIN current_questions cq
            ON cq.version_id=v.id JOIN questions q ON q.id=v.question_id WHERE q.unit_id=?''', (self.unit,)).fetchall():
            version = str(uuid.uuid4())
            self.db.execute('INSERT INTO question_versions VALUES (?,?,?,?,?,?)',
                (version, row['question_id'], version, row['payload'], row['difficulty'], row['created_at']))
            self.db.execute('UPDATE current_questions SET version_id=? WHERE question_id=?', (version, row['question_id']))
        self.db.commit()
        self.finish(self.begin())
        self.assertEqual(self.summary(), expected)

    def test_backup_isolation_and_account_deletion(self):
        attempt = self.begin()
        self.finish(attempt)
        expected = self.summary()
        backup = self.path.with_name('reward-backup.sqlite3')
        copy_database(self.path, backup)
        with closing(connect(backup)) as restored:
            self.assertEqual(rewards_summary(restored, self.owner), expected)
        other = self.app.test_client()
        self.register(other, 'student_2')
        other_id = self.db.execute('SELECT id FROM users WHERE username=?', ('student_2',)).fetchone()[0]
        self.assertEqual(rewards_summary(self.db, other_id)['xp'], 0)
        self.finish(self.begin(owner=other_id))
        token = self.csrf(self.client, '/account/delete')
        self.assertEqual(self.client.post('/account/delete', data=dict(csrf=token,
            current_password=self.password, confirmation='ΔΙΑΓΡΑΦΗ')).status_code, 200)
        self.assertEqual(self.summary()['xp'], 0)
        self.assertEqual(rewards_summary(self.db, other_id)['xp'], expected['xp'])
