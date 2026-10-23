import copy
import html
import json
import re
import unittest
from database import ROOT
from database.importer import add_question_version
from database.question_content import apply_release, validate_release, deploy_releases
from tests.support import DatabaseCase


def release():
    return json.loads((ROOT/'content/questions/gym-a-algebra.v1.json').read_text(encoding='utf-8'))


class QuestionValidationTests(unittest.TestCase):
    def test_all_authored_questions_and_coverage(self):
        prepared=validate_release(release())
        self.assertEqual(len(prepared),144)
        units={u['id'] for u,_,_,_ in prepared}
        self.assertEqual(len(units),24)
        for uid in units:
            rows=[(u,p) for u,_,_,p in prepared if u['id']==uid]
            for level in ['easy','medium','hard']:
                self.assertEqual(sum(p['difficulty']==level for _,p in rows),2)
            self.assertEqual({o for _,p in rows for o in p['objective_ids']},{o['id'] for o in rows[0][0]['learning_objectives']})

    def test_rejects_wrong_answers_and_equivalent_options(self):
        for change in ['wrong','equivalent','duplicate']:
            r=release();p=r['entries'][0]['payload']
            if change=='wrong':p['answer']=p['choices'][1]
            if change=='equivalent':p['choices'][1]='7000/1'
            if change=='duplicate':p['choices'][1]=' 7000 '
            with self.subTest(change=change),self.assertRaises(ValueError):validate_release(r)

    def test_rejects_bad_metadata_duplicate_prompts_and_delimiters(self):
        mutations=[lambda r:r['entries'][0]['payload'].update(hint=''),
                   lambda r:r['entries'][0]['payload'].update(solution=''),
                   lambda r:r['entries'][0]['payload'].update(objective_ids=['foreign-objective']),
                   lambda r:r['entries'][0]['payload'].update(source_refs=[]),
                   lambda r:r['entries'][0]['payload'].update(question=r'Broken \\(x\\)'),
                   lambda r:r['entries'][0]['payload'].update(question=r'Broken \(x'),
                   lambda r:r['entries'][1]['payload'].update(question=r['entries'][0]['payload']['question'])]
        for mutate in mutations:
            r=release();mutate(r)
            with self.assertRaises(ValueError):validate_release(r)

    def test_arithmetic_checks_reject_code(self):
        r=release();r['entries'][0]['payload']['verification']['expression']='__import__("os").system("unsafe")'
        with self.assertRaises(ValueError):validate_release(r)


class QuestionReleaseTests(DatabaseCase):
    def test_atomic_baseline_and_idempotence_preserve_legacy(self):
        old=[tuple(r) for r in self.db.execute('SELECT * FROM question_versions ORDER BY id')]
        r=release();self.assertEqual(apply_release(self.db,r),144)
        self.assertEqual(apply_release(self.db,r),0)
        for row in old:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM question_versions WHERE id=?',(row[0],)).fetchone()),row)
        updated=copy.deepcopy(r);updated['entries']=updated['entries'][:2]
        for entry in updated['entries']:
            qid=validate_release({**r,'entries':[entry]})[0][2]
            entry['expected_current']=self.db.execute('SELECT version_id FROM current_questions WHERE question_id=?',(qid,)).fetchone()[0]
            entry['payload']['hint']+=' Έλεγξε προσεκτικά.'
        updated['entries'][1]['expected_current']='stale-baseline'
        pointers=[tuple(r) for r in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')]
        with self.assertRaises(ValueError):apply_release(self.db,updated)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')],pointers)

    def test_attempts_keep_original_question_version_and_solutions(self):
        r=release();apply_release(self.db,r)
        unit,_,qid,payload=validate_release(r)[0]
        attempt=self.repo.start_attempt(unit['id'],'easy')
        old_questions=copy.deepcopy(attempt['questions'])
        newer=copy.deepcopy(r);newer['entries']=newer['entries'][:1]
        newer['entries'][0]['expected_current']=next(q['version_id'] for q in old_questions if q['question']==payload['question'])
        newer['entries'][0]['payload']['solution']+=' Πρόσθετη διευκρίνιση.'
        self.assertEqual(apply_release(self.db,newer),1)
        self.assertEqual(self.repo.attempt(attempt['id'])['questions'],old_questions)
        with self.assertRaisesRegex(ValueError,'manual review'):deploy_releases(self.db)

    def test_all_new_quizzes_filters_scores_hints_and_solutions(self):
        r=release();apply_release(self.db,r)
        units={u['id']:u for u,_,_,_ in validate_release(r)}
        for uid,unit in units.items():
            for level in ['all','easy','medium','hard']:
                for mode in ['correct','wrong','blank']:
                    url='/quiz/unit/'+uid
                    response=self.client.get(url+'?difficulty='+level)
                    self.assertEqual(response.status_code,200)
                    token=re.search(rb'name="attempt_token" value="([^"]+)"',response.data)[1].decode()
                    attempt=self.repo.attempt(self.signer.loads(token)['attempt_id'])
                    self.assertEqual(attempt['total'],6 if level=='all' else 2)
                    self.assertIn('Χρειάζεσαι μια υπόδειξη;'.encode(),response.data)
                    self.assertNotIn('Πώς προκύπτει:'.encode(),response.data)
                    if unit['teaching_scope']=='optional':self.assertIn('Προαιρετική ενότητα'.encode(),response.data)
                    form={'attempt_token':token,'difficulty':level}
                    for i,q in enumerate(attempt['questions']):
                        if mode!='blank':form[f'question_{i}']=q['answer'] if mode=='correct' else next(c for c in q['choices'] if c!=q['answer'])
                    result=self.client.post(url,data=form)
                    self.assertEqual(result.status_code,200)
                    expected=attempt['total'] if mode=='correct' else 0
                    self.assertEqual(self.repo.attempt(attempt['id'])['score'],expected)
                    self.assertIn('Πώς προκύπτει:'.encode(),result.data)
                    for q in attempt['questions']:self.assertIn(q['solution'],html.unescape(result.get_data(as_text=True)))
                    again=self.client.post(url,data=form)
                    self.assertEqual(again.data,result.data)
