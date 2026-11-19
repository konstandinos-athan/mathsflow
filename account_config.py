"""Explicit deployment settings; no account activation from truthy strings."""
import os


def account_environment(environ=None):
    env = os.environ if environ is None else environ
    result = {}
    for key in ('AUTH_ENABLED', 'AUTH_PERSISTENT_STORAGE'):
        raw = env.get(key, 'false').strip().lower()
        if raw not in ('true', 'false'):
            raise RuntimeError(f'{key} must be true or false')
        result[key] = raw == 'true'
    for key in ('PRIVACY_CONTROLLER', 'PRIVACY_CONTACT'):
        result[key] = env.get(key, '').strip()
    return result
