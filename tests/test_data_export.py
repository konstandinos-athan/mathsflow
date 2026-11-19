import re
from tests.support import DatabaseCase


class DataExportTests(DatabaseCase):
    password = 'correct horse battery SAMPLE'

    def token(self, client, path):
        page = client.get(path)
        self.assertEqual(page.status_code, 200)
        return re.search(rb'name="csrf" value="([^"]+)"', page.data)[1].decode()

    def register(self, client, name):
        home = client.get('/')
        self.assertIn('Δημιουργία προφίλ'.encode(), home.data)
        response = client.post('/account/register', data=dict(
            csrf=self.token(client, '/account/register'), username=name,
            password=self.password, confirm=self.password, age_15='yes', privacy='yes'))
        self.assertEqual(response.status_code, 200)

    def test_export_own_account_only_without_security_secrets(self):
        self.app.config['AUTH_ENABLED'] = True
        self.register(self.client, 'first_student')
        for url in ('/', '/data-rights', '/contact'):
            self.assertEqual(self.client.get(url).headers['Cache-Control'], 'no-store')
        other = self.app.test_client()
        self.register(other, 'second_student')
        other_id = self.db.execute('SELECT id FROM users WHERE username=?', ('second_student',)).fetchone()[0]
        response = self.client.post('/account/export', data=dict(
            csrf=self.token(self.client, '/account/export'), current_password=self.password, user_id=other_id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['account']['username'], 'first_student')
        self.assertNotIn('second_student', response.get_data(as_text=True))
        self.assertNotIn(other_id, response.get_data(as_text=True))
        for secret in ('password_hash', 'recovery_hash', 'auth_token', 'token_hash'):
            self.assertNotIn(secret, response.get_data(as_text=True))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn('attachment;', response.headers['Content-Disposition'])

    def test_export_requires_enabled_account_csrf_and_fresh_password(self):
        self.assertEqual(self.client.get('/account/export').status_code, 404)
        self.app.config['AUTH_ENABLED'] = True
        self.assertEqual(self.client.get('/account/export').status_code, 401)
        self.register(self.client, 'first_student')
        self.assertEqual(self.client.post('/account/export', data={'current_password': self.password}).status_code, 400)
        token = self.token(self.client, '/account/export')
        response = self.client.post('/account/export', data=dict(csrf=token, current_password='wrong'))
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('Content-Disposition', response.headers)
        for _ in range(5):
            response = self.client.post('/account/export', data=dict(csrf=token, current_password='wrong'))
        self.assertEqual(response.status_code, 429)

    def test_export_complete_history_and_rewards_are_isolated(self):
        self.app.config['AUTH_ENABLED'] = True
        self.register(self.client, 'first_student')
        other = self.app.test_client()
        self.register(other, 'second_student')
        owners = dict(self.db.execute('SELECT username,id FROM users'))
        unit = self.repo.legacy_unit('gel', 'a-gel', 'algebra', 1)['id']
        own_attempts = []
        # More than the dashboard page size, including pending and submitted work.
        for index in range(22):
            attempt = self.repo.start_attempt(unit, 'all', user_id=owners['first_student'])
            own_attempts.append(attempt)
            if index == 0:
                self.repo.submit_attempt(attempt['id'], unit, 'all',
                    {f'question_{i}': q['answer'] for i, q in enumerate(attempt['questions'])})
        foreign = self.repo.start_attempt(unit, 'all', user_id=owners['second_student'])
        self.repo.submit_attempt(foreign['id'], unit, 'all',
            {f'question_{i}': q['answer'] for i, q in enumerate(foreign['questions'])})
        anonymous = self.repo.start_attempt(unit, 'all')
        response = self.client.post('/account/export', data=dict(
            csrf=self.token(self.client, '/account/export'), current_password=self.password))
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual({a['id'] for a in payload['attempts']}, {a['id'] for a in own_attempts})
        self.assertEqual(len(payload['responses']), own_attempts[0]['total'])
        self.assertTrue(all(r['correct'] == 1 for r in payload['responses']))
        self.assertEqual(sum(r['xp'] for r in payload['rewards']), own_attempts[0]['total'] * 10)
        for private_id in (foreign['id'], anonymous['id'], owners['second_student']):
            self.assertNotIn(private_id, response.get_data(as_text=True))
