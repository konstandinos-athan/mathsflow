import re
import unittest
from unittest.mock import patch
from itsdangerous import SignatureExpired
from tests.support import DatabaseCase
from database.importer import add_question_version


class ApplicationTests(DatabaseCase):
    url = '/quiz/gel/a-gel/algebra/1'

    def attempt(self, url=None):
        response = self.client.get(url or self.url)
        self.assertEqual(response.status_code, 200)
        token = re.search(rb'name="attempt_token" value="([^"]+)"', response.data)[1].decode()
        return token, self.repo.attempt(self.signer.loads(token)['attempt_id'])

    def test_all_catalog_and_legacy_routes_and_filters(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        for school_key, school in self.repo.navigation().items():
            self.assertEqual(self.client.get(f'/school/{school_key}').status_code, 200)
            for grade_key, grade in school['classes'].items():
                self.assertEqual(self.client.get(f'/school/{school_key}/{grade_key}').status_code, 200)
                for subject_key, subject in grade['subjects'].items():
                    self.assertEqual(self.client.get(f'/school/{school_key}/{grade_key}/{subject_key}').status_code, 200)
                    for lesson in subject['lessons']:
                        with self.subTest(unit=lesson['id']):
                            self.assertEqual(self.client.get('/study/unit/' + lesson['id']).status_code, 200)
                            for difficulty in ('all', 'easy', 'medium', 'hard'):
                                self.assertEqual(self.client.get('/quiz/unit/' + lesson['id'] + '?difficulty=' + difficulty).status_code, 200)
        for route in self.db.execute('SELECT * FROM legacy_routes').fetchall():
            suffix = '/'.join(str(route[k]) for k in ('school_key','grade_key','subject_key','lesson_id'))
            for prefix in ('/study/', '/quiz/'):
                self.assertEqual(self.client.get(prefix + suffix).status_code, 200)
        self.assertEqual(self.client.get('/school/gel/g-gel/algebra').status_code, 200)

    def test_correct_wrong_and_unanswered_grading_across_catalog(self):
        for unit in self.db.execute('SELECT DISTINCT unit_id FROM questions').fetchall():
            for difficulty in ('all', 'easy', 'medium', 'hard'):
                url = '/quiz/unit/' + unit[0] + '?difficulty=' + difficulty
                for mode in ('correct', 'wrong', 'unanswered'):
                    with self.subTest(unit=unit[0], difficulty=difficulty, mode=mode):
                        token, attempt = self.attempt(url)
                        self.attempt(url)  # Another tab does not change the first attempt.
                        form = {'difficulty': difficulty, 'attempt_token': token}
                        for i, q in enumerate(attempt['questions']):
                            if mode == 'correct': form[f'question_{i}'] = q['answer']
                            if mode == 'wrong': form[f'question_{i}'] = next(c for c in q['choices'] if c != q['answer'])
                        response = self.client.post('/quiz/unit/' + unit[0], data=form)
                        self.assertEqual(response.status_code, 200)
                        expected = attempt['total'] if mode == 'correct' else 0
                        self.assertIn(f'{expected} / {attempt["total"]}'.encode(), response.data)
                        saved = self.repo.attempt(attempt['id'])
                        self.assertEqual(saved['score'], expected)
                        self.assertEqual(len(saved['user_answers']), attempt['total'])

    def test_invalid_missing_and_expired_tokens(self):
        token, _ = self.attempt()
        for value in ('', token+'x', 'invalid'):
            self.assertEqual(self.client.post(self.url, data={'attempt_token': value}).status_code, 400)
        with patch.object(self.signer, 'loads', side_effect=SignatureExpired('expired')):
            self.assertEqual(self.client.post(self.url, data={'attempt_token': token}).status_code, 400)

    def test_context_and_content_versions(self):
        token, attempt = self.attempt()
        self.assertEqual(self.client.post(self.url, data={'attempt_token': token, 'difficulty': 'easy'}).status_code, 400)
        self.assertEqual(self.client.post('/quiz/gel/a-gel/algebra/2', data={'attempt_token': token}).status_code, 400)
        question = attempt['questions'][0]
        question_id = self.db.execute('SELECT question_id FROM question_versions WHERE id=?', (question['version_id'],)).fetchone()[0]
        changed = dict(question)
        changed.pop('version_id')
        changed['question'] = 'Edited prompt'
        changed['answer'] = next(x for x in changed['choices'] if x != question['answer'])
        add_question_version(self.db, question_id, changed)
        self.db.commit()
        form = {'attempt_token': token, **{f'question_{i}': q['answer'] for i,q in enumerate(attempt['questions'])}}
        self.assertEqual(self.client.post(self.url, data=form).status_code, 200)
        self.assertEqual(self.repo.attempt(attempt['id'])['score'], attempt['total'])

    def test_duplicate_submission_keeps_first_result(self):
        token, attempt = self.attempt()
        form = {'attempt_token': token}
        self.assertEqual(self.client.post(self.url, data=form).status_code, 200)
        form.update({f'question_{i}': q['answer'] for i,q in enumerate(attempt['questions'])})
        self.assertEqual(self.client.post(self.url, data=form).status_code, 200)
        self.assertEqual(self.repo.attempt(attempt['id'])['score'], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM responses WHERE attempt_id=?', (attempt['id'],)).fetchone()[0], attempt['total'])

    def test_malformed_payload_and_invalid_choice(self):
        token, _ = self.attempt()
        payload = self.signer.loads(token)
        for value in ([], {}, {**payload,'attempt_id': 22}, {**payload,'attempt_id': 'unknown'}):
            self.assertEqual(self.client.post(self.url,data={'attempt_token': self.signer.dumps(value)}).status_code,400)
        self.assertEqual(self.client.post(self.url,data={'attempt_token':token,'question_0':'not-a-choice'}).status_code,400)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM responses').fetchone()[0], 0)

    def test_invalid_routes_and_filter(self):
        for path in ('/school/missing','/school/gel/missing','/school/gel/a-gel/missing', '/study/gel/a-gel/algebra/0','/quiz/gel/a-gel/algebra/999','/study/unit/00000000-0000-0000-0000-000000000000'):
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertEqual(self.client.get(self.url+'?difficulty=invalid').status_code,400)
        self.assertEqual(self.client.post(self.url,data={'difficulty':'invalid'}).status_code,400)

    def test_static_assets(self):
        for path in ('/favicon.ico','/static/favicon.png','/static/css/style.css','/static/js/script.js'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            response.close()

    def test_get_does_not_expose_correct_answer_metadata(self):
        response=self.client.get(self.url)
        self.assertNotIn(b'correct_answer',response.data)
        self.assertNotIn(b'"answer":',response.data)
        self.assertNotIn(b'version_id',response.data)


if __name__=='__main__': unittest.main()
