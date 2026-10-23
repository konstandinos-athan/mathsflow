"""Fixtures use disposable databases; tests never mutate the user's real database."""
import tempfile
import unittest
from pathlib import Path
from database import ROOT, connect, migrate
from database.importer import import_data
from database.repository import Repository
from app import create_app


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / 'instance' / 'test-runs'
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.sqlite3'
        self.db = connect(self.path, create=True)
        self.addCleanup(self.db.close)
        migrate(self.db)
        import_data(self.db)
        self.repo = Repository(self.db)
        self.app = create_app({'TESTING': True, 'DATABASE': str(self.path), 'SECRET_KEY': 'test-only-key'})
        self.client = self.app.test_client()
        self.signer = self.app.extensions['quiz_signer']
