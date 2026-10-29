import re
import time
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from werkzeug.datastructures import MultiDict
from tests.support import DatabaseCase
from database import ROOT, connect, migrate, copy_database, check
from database.repository import Repository
from database.importer import import_data


class Stage6Tests(DatabaseCase):
    url = '/quiz/gel/a-gel/algebra/1'

    def begin(self, mode='practice'):
        page = self.client.get(self.url + '?mode=' + mode)
        self.assertEqual(page.status_code, 200)
        token = re.search(rb'name="attempt_token" value="([^"]+)"', page.data)[1].decode()
        return token, self.repo.attempt(self.signer.loads(token)['attempt_id']), page

    def test_exam_hides_hints_and_solution_until_submission(self):
        token, attempt, page = self.begin('exam')
        self.assertNotIn(b'class="quiz-hint"', page.data)
        self.assertNotIn('Πώς προκύπτει:'.encode(), page.data)
        response = self.client.post(self.url, data={'attempt_token': token, 'mode': 'exam',
            **{f'question_{i}': q['answer'] for i,q in enumerate(attempt['questions'])}})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'20.0 / 20', response.data)
        self.assertIn(b'100.0%', response.data)
        self.assertIn('disabled'.encode(), response.data)

    def test_mixed_score_blank_and_saved_result_survives_new_client(self):
        token, attempt, _ = self.begin()
        questions = attempt['questions']
        form = {'attempt_token': token, 'question_0': questions[0]['answer'],
                'question_1': next(c for c in questions[1]['choices'] if c != questions[1]['answer'])}
        self.assertEqual(self.client.post(self.url, data=form).status_code, 200)
        saved = self.repo.attempt(attempt['id'])
        self.assertEqual(saved['grading'], dict(correct=1, wrong=1, unanswered=attempt['total']-2,
            percent=round(100/attempt['total'],1),out_of_twenty=round(20/attempt['total'],1)))
        count = self.db.execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0]
        # Result links don't expire at the two-hour submission deadline or create new attempts.
        with patch('itsdangerous.timed.time.time', return_value=time.time()+9000):
            page = self.app.test_client().get('/quiz/result/'+token)
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'1 / {attempt["total"]}'.encode(), page.data)
        self.assertEqual(page.headers['Cache-Control'], 'no-store')
        self.assertEqual(page.headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(count, self.db.execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0])

    def test_results_unavailable_before_submit_or_for_tampered_context(self):
        token, attempt, _ = self.begin()
        self.assertEqual(self.client.get('/quiz/result/'+token).status_code,404)
        self.client.post(self.url,data={'attempt_token':token})
        payload=self.signer.loads(token)
        for bad in (token+'x',self.signer.dumps([]),self.signer.dumps({**payload,'mode':'exam'}),self.signer.dumps({**payload,'unit_id':'other'})):
            self.assertEqual(self.client.get('/quiz/result/'+bad).status_code,404)

    def test_invalid_duplicate_unknown_and_oversized_input_is_atomic(self):
        token, attempt, _ = self.begin()
        valid={'attempt_token':token,'question_0':attempt['questions'][0]['answer']}
        forms=[{**valid,'question_1':'<script>alert(1)</script>'}, {**valid,'question_999':'0'},
               {**valid,'score':'999'}, MultiDict([*valid.items(),('question_0','other')]),
               MultiDict([*valid.items(),('difficulty','all'),('difficulty','easy')])]
        for form in forms:
            self.assertEqual(self.client.post(self.url,data=form).status_code,400)
            self.assertIsNone(self.repo.attempt(attempt['id'])['score'])
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM responses').fetchone()[0],0)
        self.assertEqual(self.client.post(self.url,data={**valid,'question_0':'x'*70000}).status_code,413)

    def test_exam_mode_cannot_be_changed_on_submit_and_invalid_modes_fail(self):
        token, attempt, _ = self.begin('exam')
        self.assertEqual(self.client.post(self.url,data={'attempt_token':token,'mode':'practice'}).status_code,400)
        self.assertEqual(self.client.get(self.url+'?mode=other').status_code,400)
        self.assertEqual(self.client.get(self.url+'?mode=exam&mode=practice').status_code,400)

    def test_expired_open_attempt_rejected_but_completed_repository_retry_stable(self):
        token, attempt, _ = self.begin()
        with patch('database.repository.time.time',return_value=attempt['started_at']+7201):
            with self.assertRaises(ValueError):
                self.repo.submit_attempt(attempt['id'],attempt['unit_id'],'all',{})
        first=self.repo.submit_attempt(attempt['id'],attempt['unit_id'],'all',{})
        with patch('database.repository.time.time',return_value=attempt['started_at']+7201):
            again=self.repo.submit_attempt(attempt['id'],attempt['unit_id'],'all',{})
        self.assertEqual(first['score'],again['score'])

    def test_concurrent_conflicting_submissions_commit_only_one_result(self):
        _, attempt, _=self.begin()
        barrier=threading.Barrier(2)
        def submit(correct):
            db=connect(self.path)
            try:
                answers={f'question_{i}':q['answer'] for i,q in enumerate(attempt['questions'])} if correct else {}
                barrier.wait(timeout=10)
                return Repository(db).submit_attempt(attempt['id'],attempt['unit_id'],'all',answers)['score']
            finally: db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(submit,[True,False]))
        self.assertEqual(results[0],results[1])
        self.assertIn(results[0],(0,attempt['total']))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM responses').fetchone()[0],attempt['total'])

    def test_previous_schema_backup_migrate_and_restore_preserve_attempt(self):
        directory=Path(self.tmp.name)/'old-migrations';directory.mkdir()
        for source in sorted((ROOT/'migrations').glob('*.sql'))[:3]: shutil.copy2(source,directory/source.name)
        path=Path(self.tmp.name)/'old.sqlite3'
        old=connect(path,create=True)
        try:
            migrate(old,directory);import_data(old)
            uid=old.execute('SELECT unit_id FROM questions LIMIT 1').fetchone()[0]
            old.execute('INSERT INTO quiz_attempts(id,unit_id,difficulty,started_at,total) VALUES (?,?,?,?,?)',('old',uid,'all',time.time(),1));old.commit()
            backup=Path(self.tmp.name)/'backup.sqlite3'
            copy_database(path,backup,allow_pending=True)
            migrate(old);migrate(old);check(old)
            self.assertEqual(old.execute('SELECT mode FROM quiz_attempts WHERE id=?',('old',)).fetchone()[0],'practice')
            restored=Path(self.tmp.name)/'restored.sqlite3'
            copy_database(backup,restored,allow_pending=True)
            db=connect(restored)
            try:
                self.assertNotIn('mode',[r['name'] for r in db.execute('PRAGMA table_info(quiz_attempts)')])
                migrate(db);check(db)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0],1)
            finally:db.close()
        finally:old.close()

    def test_multiple_choice_equivalent_values_are_not_injected(self):
        token, attempt, _=self.begin()
        answer=attempt['questions'][0]['answer']
        self.assertEqual(self.client.post(self.url,data={'attempt_token':token,'question_0':answer+' '}).status_code,400)
        self.assertEqual(self.client.post(self.url,data={'attempt_token':token,'question_0':answer}).status_code,200)
