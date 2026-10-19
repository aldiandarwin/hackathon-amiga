"""HTTP boundary checks using synthetic sessions; no database, worker, AI or filesystem changes."""
from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings

SECRET = 'synthetic-proxy-secret-for-tests-only'


def synthetic_app(settings):
    db = Mock()
    db.login.return_value = ('synthetic-session', 'synthetic-csrf')
    db.session.side_effect = lambda token: ({'id': 'synthetic-user', 'csrf': 'synthetic-csrf', 'role': 'PIC'}
                                           if token == 'synthetic-session' else None)
    service = Mock(db=db, settings=settings)
    with patch('app.main.Database', return_value=db), patch('app.main.InvoiceService', return_value=service), \
            patch('app.main.ReviewService'):
        api = create_app(settings, start_worker=False)
    return api, db


class VercelProxyTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings('unused', 'unused', public_base_url='https://amiga.test',
                                 proxy_secret=SECRET, secure_cookies=True)
        api, self.db = synthetic_app(self.settings)
        # No lifespan is entered: this exercises real HTTP middleware and auth routes without storage.
        self.client = TestClient(api, base_url='https://127.0.0.1:8787',
                                 headers={'x-amiga-proxy-secret': SECRET, 'origin': 'https://amiga.test'})

    def login(self):
        return self.client.post('/api/v1/login', json={'email': 'synthetic@amiga.test', 'password': 'synthetic-only'})

    def test_https_login_sets_secure_cookie_and_authenticates_session(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        for flag in ('Secure', 'HttpOnly', 'SameSite=strict', 'Path=/'):
            self.assertIn(flag, response.headers['set-cookie'])
        self.assertEqual(self.client.get('/api/v1/session').status_code, 200)

    def test_proxy_secret_is_required_even_for_reads_and_public_pages(self):
        for path in ('/api/v1/health', '/review', '/static/app.css', '/verifikasi/synthetic'):
            for secret in ('', 'wrong'):
                response = self.client.get(path, headers={'x-amiga-proxy-secret': secret})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.headers['cache-control'], 'no-store')
        self.db.login.assert_not_called()

    def test_untrusted_origin_and_host_are_rejected_despite_valid_secret(self):
        for origin in ('http://amiga.test', 'https://attacker.test', 'http://127.0.0.1:3000', 'null'):
            response = self.client.post('/api/v1/login', headers={'origin': origin},
                                        json={'email': 'synthetic@amiga.test', 'password': 'synthetic-only'})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/api/v1/health', headers={'host': 'attacker.test'}).status_code, 400)
        self.db.login.assert_not_called()

    def test_secret_does_not_replace_session_or_csrf(self):
        self.assertEqual(self.client.post('/api/v1/logout').status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.post('/api/v1/logout').json()['code'], 'CSRF_REJECTED')
        self.assertEqual(self.client.post('/api/v1/logout', headers={'x-csrf-token': 'wrong'}).status_code, 403)
        response = self.client.post('/api/v1/logout', headers={'x-csrf-token': 'synthetic-csrf'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Secure', response.headers['set-cookie'])

    def test_local_demo_remains_usable_without_proxy_secret(self):
        settings = replace(self.settings, public_base_url='http://127.0.0.1:3000', proxy_secret='', secure_cookies=False)
        api, _ = synthetic_app(settings)
        client = TestClient(api, base_url='http://127.0.0.1:8787')
        self.assertEqual(client.get('/api/v1/health').status_code, 200)
        response = client.post('/api/v1/login', headers={'origin': 'http://127.0.0.1:3000'},
                               json={'email': 'synthetic@amiga.test', 'password': 'synthetic-only'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Secure', response.headers['set-cookie'])

    def test_settings_read_deployment_variables_and_hide_secret(self):
        values = {'AMIGA_DATABASE_URL': 'unused', 'AMIGA_DEMO_PASSWORD': 'unused'}
        with patch('app.settings.read_dotenv', return_value=values), patch.dict('os.environ', {
                'AMIGA_PUBLIC_BASE_URL': 'https://amiga.test', 'AMIGA_PROXY_SECRET': SECRET}):
            settings = Settings.load()
        self.assertTrue(settings.secure_cookies)
        self.assertNotIn(SECRET, repr(settings))
        for public, secret in [('http://amiga.test', SECRET), ('https://amiga.test/path', SECRET),
                               ('https://amiga.test', 'short')]:
            with patch('app.settings.read_dotenv', return_value=values), patch.dict('os.environ', {
                    'AMIGA_PUBLIC_BASE_URL': public, 'AMIGA_PROXY_SECRET': secret}):
                with self.assertRaises(ValueError):
                    Settings.load()


if __name__ == '__main__':
    unittest.main()
