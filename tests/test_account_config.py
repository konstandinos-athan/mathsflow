import os
import unittest
from unittest.mock import patch
from account_config import account_environment
from app import create_app


class AccountConfigurationTests(unittest.TestCase):
    def test_defaults_and_explicit_boolean_values(self):
        self.assertFalse(account_environment({})['AUTH_ENABLED'])
        self.assertFalse(account_environment({'AUTH_ENABLED': 'false'})['AUTH_ENABLED'])
        values = account_environment({'AUTH_ENABLED': ' TRUE ', 'AUTH_PERSISTENT_STORAGE': 'true',
                                     'PRIVACY_CONTROLLER': ' Example ', 'PRIVACY_CONTACT': ' contact@example.invalid '})
        self.assertTrue(values['AUTH_ENABLED'])
        self.assertTrue(values['AUTH_PERSISTENT_STORAGE'])
        self.assertEqual(values['PRIVACY_CONTROLLER'], 'Example')
        for raw in ('yes', '1', '0', '', 'enabled'):
            with self.assertRaises(RuntimeError):
                account_environment({'AUTH_ENABLED': raw})

    def test_production_environment_keeps_existing_guards(self):
        env = {'MATHSFLOW_ENV': 'production', 'SECRET_KEY': 'test-only-configuration-key',
               'AUTH_ENABLED': 'true'}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                create_app()
        with patch.dict(os.environ, {**env, 'AUTH_PERSISTENT_STORAGE': 'true',
                                    'PRIVACY_CONTROLLER': 'Test controller',
                                    'PRIVACY_CONTACT': 'test@example.invalid'}, clear=True):
            app = create_app()
            self.assertTrue(app.config['AUTH_ENABLED'])
            self.assertTrue(app.config['SESSION_COOKIE_SECURE'])
            self.assertEqual(app.config['PRIVACY_CONTROLLER'], 'Test controller')
            # Explicit test/local configuration remains possible without changing the environment.
            disabled = create_app({'AUTH_ENABLED': False})
            self.assertEqual(disabled.test_client().get('/account/register').status_code, 404)
