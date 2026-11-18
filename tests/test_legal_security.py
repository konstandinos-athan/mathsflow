from tests.support import DatabaseCase
from app import create_app


class LegalSecurityTests(DatabaseCase):
    def test_math_cdn_only_on_pages_that_render_math(self):
        self.app.config['AUTH_ENABLED'] = True
        for url in ('/', '/privacy', '/cookies', '/terms', '/ai-policy', '/data-rights',
                    '/contact', '/accessibility', '/account/login', '/account/register'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(b'src="https://cdn.jsdelivr.net', response.data)
        for url in ('/study/gel/a-gel/algebra/1', '/quiz/gel/a-gel/algebra/1'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'src="https://cdn.jsdelivr.net', response.data)

    def test_public_policies_available_without_account_or_cookie(self):
        for url in ('/privacy', '/cookies', '/terms', '/ai-policy', '/data-rights', '/contact', '/accessibility'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Προσχέδιο'.encode(), response.data)
            self.assertNotIn('Set-Cookie', response.headers)

    def test_headers_protect_public_and_error_pages(self):
        for url in ('/', '/cookies', '/does-not-exist'):
            response = self.client.get(url)
            self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
            self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
            self.assertIn("form-action 'self'", response.headers['Content-Security-Policy'])
            self.assertIn('camera=()', response.headers['Permissions-Policy'])
            self.assertNotIn('Strict-Transport-Security', response.headers)

    def test_hsts_and_secure_cookie_in_production(self):
        app = create_app(dict(TESTING=True, PRODUCTION=True, DATABASE=str(self.path),
                              SECRET_KEY='local-test-key-for-headers-only'))
        client = app.test_client()
        response = client.get('/quiz/gel/a-gel/algebra/1', base_url='https://localhost')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Strict-Transport-Security'], 'max-age=86400')
        cookie = response.headers['Set-Cookie']
        for attribute in ('Secure', 'HttpOnly', 'SameSite=Lax'):
            self.assertIn(attribute, cookie)

    def test_policies_describe_current_data_and_remain_drafts(self):
        page = self.client.get('/privacy').data.decode()
        for word in ('XP', 'Render', 'jsDelivr', 'Χρήση χωρίς λογαριασμό', '2026-11-18-draft-v2'):
            self.assertIn(word, page)
        home = self.client.get('/').data
        for url in (b'/privacy', b'/cookies', b'/terms'):
            self.assertIn(url, home)
