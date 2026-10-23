import copy
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from database import ROOT, check, connect, copy_database, migrate
from database.importer import add_question_version, add_theory_version, import_data, inputs
from database.repository import Repository
from tests.support import DatabaseCase


class StorageTests(DatabaseCase):
    def first_unit(self):
        return self.db.execute('SELECT unit_id FROM questions LIMIT 1').fetchone()[0]

    def test_import_is_lossless(self):
        catalog, sources, legacy = inputs()
        self.assertEqual(check(self.db)['units'], 325)
        self.assertEqual(check(self.db)['questions'], 480)
        self.assertEqual([json.loads(r[0]) for r in self.db.execute('SELECT payload FROM units ORDER BY rowid')], catalog['units'])
        for unit_id, content in legacy.items():
            self.assertEqual(self.repo.theory(unit_id), content['theory'])
            questions = [{k:v for k,v in q.items() if k!='version_id'} for q in self.repo.questions(unit_id)]
            self.assertEqual(questions, content['questions'])

    def test_import_and_migrations_are_idempotent_and_detect_drift(self):
        before = check(self.db)
        migrate(self.db)
        import_data(self.db)
        self.assertEqual(check(self.db), before)
        catalog, sources, legacy = inputs()
        catalog = copy.deepcopy(catalog)
        catalog['units'][0]['title'] += ' changed'
        with self.assertRaisesRegex(ValueError,'inputs changed'):
            import_data(self.db, catalog, sources, legacy)
        self.assertEqual(check(self.db), before)

    def test_invalid_import_rolls_back_every_row(self):
        path = Path(self.tmp.name) / 'invalid.sqlite3'
        connection = connect(path, create=True)
        self.addCleanup(connection.close)
        migrate(connection)
        catalog, sources, legacy = inputs()
        legacy = copy.deepcopy(legacy)
        content = next(v for v in legacy.values() if v['questions'])
        content['questions'][0]['answer'] = 'not-in-choices'
        with self.assertRaises(ValueError): import_data(connection,catalog,sources,legacy)
        self.assertEqual(connection.execute('SELECT COUNT(*) FROM schools').fetchone()[0],0)
        self.assertEqual(connection.execute('SELECT COUNT(*) FROM units').fetchone()[0],0)
        self.assertEqual(connection.execute('SELECT COUNT(*) FROM import_runs').fetchone()[0],0)

    def test_new_question_and_theory_versions_preserve_old_attempt(self):
        unit = self.first_unit()
        attempt = self.repo.start_attempt(unit,'all')
        original = attempt['questions'][0]
        question_id = self.db.execute('SELECT question_id FROM question_versions WHERE id=?',(original['version_id'],)).fetchone()[0]
        payload = {k:v for k,v in original.items() if k!='version_id'}
        payload['question'] = 'Revised question'
        payload['answer'] = next(x for x in payload['choices'] if x != original['answer'])
        version_id = add_question_version(self.db,question_id,payload)
        old_theory = self.repo.theory(unit)
        add_theory_version(self.db,unit,[{'title':'New theory','content':'New explanation'}])
        self.db.commit()
        self.assertNotEqual(version_id,original['version_id'])
        self.assertEqual(self.repo.attempt(attempt['id'])['questions'][0],original)
        answers={f'question_{i}':q['answer'] for i,q in enumerate(attempt['questions'])}
        saved=self.repo.submit_attempt(attempt['id'],unit,'all',answers)
        self.assertEqual(saved['score'],attempt['total'])
        versions=[json.loads(r[0]) for r in self.db.execute('SELECT blocks FROM theory_versions WHERE unit_id=?',(unit,))]
        self.assertIn(old_theory,versions)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('UPDATE question_versions SET difficulty=? WHERE id=?',('hard',original['version_id']))
        self.db.rollback()

    def test_backup_restore_preserves_history_and_never_overwrites(self):
        unit=self.first_unit()
        attempt=self.repo.start_attempt(unit,'easy')
        self.repo.submit_attempt(attempt['id'],unit,'easy',{})
        backup=Path(self.tmp.name)/'backup.sqlite3'
        restored=Path(self.tmp.name)/'restored.sqlite3'
        copy_database(self.path,backup)
        copy_database(backup,restored)
        connection=connect(restored)
        try:
            self.assertEqual(check(connection),check(self.db))
            self.assertEqual(Repository(connection).attempt(attempt['id']),self.repo.attempt(attempt['id']))
        finally:connection.close()
        before=backup.read_bytes()
        with self.assertRaises(FileExistsError):copy_database(self.path,backup)
        self.assertEqual(backup.read_bytes(),before)
        with self.assertRaises(ValueError):copy_database(self.path,self.path)

    def test_migration_upgrade_and_checksum_detection(self):
        directory=Path(self.tmp.name)/'migrations';directory.mkdir()
        first=ROOT/'migrations/001_initial.sql'
        (directory/first.name).write_bytes(first.read_bytes())
        connection=connect(Path(self.tmp.name)/'upgrade.sqlite3',create=True)
        self.addCleanup(connection.close)
        migrate(connection,directory)
        connection.execute("INSERT INTO schools VALUES ('sentinel','Preserve me')");connection.commit()
        migrate(connection)
        self.assertEqual(connection.execute("SELECT title FROM schools WHERE id='sentinel'").fetchone()[0],'Preserve me')
        (directory/first.name).write_text(first.read_text(encoding='utf-8')+'\n-- changed\n',encoding='utf-8')
        # Only the changed migration exists in this test directory; preserve all names.
        for file in (ROOT/'migrations').glob('*.sql'):
            if file.name!=first.name:(directory/file.name).write_bytes(file.read_bytes())
        with self.assertRaisesRegex(ValueError,'migration changed'):migrate(connection,directory)

    def test_failed_migration_is_atomic(self):
        directory=Path(self.tmp.name)/'broken';directory.mkdir()
        (directory/'001_broken.sql').write_text('CREATE TABLE before_failure(id INTEGER);\nINVALID SQL;\n',encoding='utf-8')
        connection=connect(Path(self.tmp.name)/'broken.sqlite3',create=True)
        self.addCleanup(connection.close)
        with self.assertRaises(sqlite3.OperationalError):migrate(connection,directory)
        self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='before_failure'").fetchone())

    def test_foreign_keys_and_wrong_revision_owner(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO user_progress VALUES ('missing','missing',0,0)")
        self.db.rollback()
        rows=self.db.execute('SELECT question_id,version_id FROM current_questions LIMIT 2').fetchall()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('UPDATE current_questions SET version_id=? WHERE question_id=?',(rows[1]['version_id'],rows[0]['question_id']))
        self.db.rollback()

    def test_simultaneous_submissions_have_one_immutable_result(self):
        unit=self.first_unit();attempt=self.repo.start_attempt(unit,'easy')
        correct={f'question_{i}':q['answer'] for i,q in enumerate(attempt['questions'])}
        def submit(answers):
            connection=connect(self.path)
            try:return Repository(connection).submit_attempt(attempt['id'],unit,'easy',answers)['score']
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool: scores=list(pool.map(submit,[{},correct]))
        self.assertEqual(scores[0],scores[1])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM responses WHERE attempt_id=?',(attempt['id'],)).fetchone()[0],attempt['total'])

    def test_expired_persisted_attempt_is_rejected(self):
        unit=self.first_unit();attempt=self.repo.start_attempt(unit,'easy')
        self.db.execute('UPDATE quiz_attempts SET started_at=? WHERE id=?',(time.time()-7300,attempt['id']));self.db.commit()
        with self.assertRaises(ValueError):self.repo.submit_attempt(attempt['id'],unit,'easy',{})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM responses').fetchone()[0],0)
