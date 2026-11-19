"""Integration checks in a new, isolated PostgreSQL schema. Never uses public data.

Reads the ignored local .env only for this explicit check. Removes only the schema
it created. Does not print the connection string or exception details.
"""
import os
import re
import sys
import unittest
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database import connect, migrate
from database.importer import import_data
from database.repository import Repository
from app import create_app
from tests import test_auth, test_data_export, test_progress, test_rewards
from tests.test_contact import ContactTests


def main():
    line = next(line for line in (ROOT / '.env').read_text().splitlines() if line.startswith('DATABASE_URL='))
    url = line.partition('=')[2]
    # Isolated schema tests require session settings, so use the direct endpoint.
    parts = urlsplit(url)
    url = urlunsplit(parts._replace(netloc=parts.netloc.replace('-pooler.', '.')))
    admin = connect(url)
    schema = 'mf_test_' + uuid.uuid4().hex
    assert re.fullmatch(r'mf_test_[0-9a-f]{32}', schema)
    admin.execute(f'CREATE SCHEMA {schema}')
    split = urlsplit(url)
    params = [(k,v) for k,v in parse_qsl(split.query) if k != 'options']
    params.append(('options', '-csearch_path='+schema))
    target = urlunsplit(split._replace(query=urlencode(params)))
    fixture = connect(target)
    try:
        migrate(fixture)
        with fixture.raw.pipeline():
            import_data(fixture)
        print('PostgreSQL schema and curriculum import PASS', flush=True)
        # Each selected test uses one preloaded schema. Account IDs are isolated by
        # deleting disposable user tables between cases, never in public schema.
        def setup(case):
            case.path = target
            case.db = connect(target)
            case.addCleanup(case.db.close)
            case.repo = Repository(case.db)
            case.app = create_app({'TESTING': True, 'DATABASE': target, 'SECRET_KEY': 'postgres-check-only'})
            case.client = case.app.test_client()
            case.signer = case.app.extensions['quiz_signer']
            case.db.execute('TRUNCATE users,quiz_attempts,auth_limits,account_deletions CASCADE')

        from tests.support import DatabaseCase
        DatabaseCase.setUp = setup
        cases = [
            (ContactTests, 'test_owned_messages_admin_reply_and_export'),
            (ContactTests, 'test_gates_csrf_and_rate_limit'),
            (test_auth.AuthTests, 'test_register_private_profile_hashing_and_no_secret_in_database_or_cookie'),
            (test_auth.AuthTests, 'test_age_privacy_and_password_required_no_account_on_error'),
            (test_auth.AuthTests, 'test_csrf_and_duplicate_fields_rejected'),
            (test_auth.AuthTests, 'test_logout_revokes_copied_session'),
            (test_auth.AuthTests, 'test_delete_removes_owned_data_and_preserves_other_users'),
            (test_data_export.DataExportTests, 'test_export_complete_history_and_rewards_are_isolated'),
            (test_rewards.RewardTests, 'test_new_student_then_level_and_badges'),
            (test_rewards.RewardTests, 'test_duplicate_and_new_exam_do_not_farm_xp'),
        ]
        suite = unittest.TestSuite(cls(name) for cls,name in cases)
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        return 0 if result.wasSuccessful() else 1
    finally:
        fixture.close()
        admin.execute(f'DROP SCHEMA {schema} CASCADE')
        admin.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print('PostgreSQL check failed:', type(error).__name__, '(details withheld to protect credentials)')
        sys.exit(1)
