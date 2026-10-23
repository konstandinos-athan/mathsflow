import json
from database import ROOT, connect, digest
from database.importer import stable
from database.theory_content import validate_release
from database.bootstrap import bootstrap
from database.importer import add_theory_version
from tests.support import DatabaseCase


class DeploymentTests(DatabaseCase):
    def test_complete_bootstrap_and_restart_preserve_attempts(self):
        unit = self.db.execute('SELECT unit_id FROM questions LIMIT 1').fetchone()[0]
        self.repo.start_attempt(unit, 'all')
        attempt_rows = [tuple(r) for r in self.db.execute('SELECT * FROM quiz_attempts')]
        expected_versions = {r[0] for r in self.db.execute('SELECT id FROM theory_versions')}
        for file in (ROOT / 'content/theory').glob('*.v*.json'):
            for u, _, blocks in validate_release(json.loads(file.read_text(encoding='utf-8'))):
                expected_versions.add(stable('theory-version/'+u['id']+'/'+digest(blocks)))
        result = bootstrap(self.path)
        self.assertEqual(result['theory_versions'], len(expected_versions))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM current_theory').fetchone()[0], 325)
        pointers = [tuple(r) for r in self.db.execute('SELECT * FROM current_theory ORDER BY unit_id')]
        self.assertEqual(bootstrap(self.path), result)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM current_theory ORDER BY unit_id')], pointers)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM quiz_attempts')], attempt_rows)

    def test_bootstrap_refuses_unpublished_content_without_overwriting(self):
        bootstrap(self.path)
        unit = self.db.execute('SELECT unit_id FROM current_theory LIMIT 1').fetchone()[0]
        version = add_theory_version(self.db, unit, [{'content': 'unpublished educator revision'}])
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'manual review'):
            bootstrap(self.path)
        self.assertEqual(self.db.execute('SELECT version_id FROM current_theory WHERE unit_id=?', (unit,)).fetchone()[0], version)
