import copy,json,unittest
from unittest.mock import patch
from database import ROOT
from database.question_content import validate_release,apply_release
from database.question_coverage import coverage
from tests.support import DatabaseCase
from tests import test_gel_a_sets as shared
def release():return json.loads((ROOT/'content/questions/gel-a-algebra.v3.json').read_text(encoding='utf-8'))
class AbsoluteValidationTests(unittest.TestCase):
 def test_support_scope_difficulties_and_objectives(self):
  from collections import Counter
  rows=validate_release(release());self.assertEqual(len(rows),30)
  self.assertEqual(Counter(p['difficulty'] for _,_,_,p in rows),{'easy':10,'medium':10,'hard':10})
  self.assertEqual({x for _,_,_,p in rows for x in p['objective_ids']},{o['id'] for o in rows[0][0]['learning_objectives']})
  self.assertTrue(all('συγκεκριμένους' in p['practice_note'] for _,_,_,p in rows))
 def test_ambiguous_implication_replaced_by_equivalence_and_proof_cases(self):
  q=release()['entries'][25]['payload'];self.assertIn('ακριβώς ισοδύναμη',q['question'])
  self.assertEqual(q['answer'],'−1<x<1');self.assertFalse(abs(1)<1);self.assertTrue(-1<=1<=1)
  self.assertNotEqual(release()['entries'][20]['payload']['question'],release()['entries'][21]['payload']['question'])
  for a in range(-8,9):
   for b in range(-8,9):
    self.assertLessEqual(abs(a+b),abs(a)+abs(b))
    self.assertEqual(abs(a+b)==abs(a)+abs(b),a*b>=0)
 def test_numeric_wrong_answer_rejected(self):
  r=release();p=r['entries'][0]['payload'];p['answer']=p['choices'][1]
  with self.assertRaises(ValueError):validate_release(r)
class AbsoluteStorageTests(DatabaseCase):
 def test_filters_all_scores_feedback_repeat_posts(self):
  with patch('tests.test_gel_a_sets.release',return_value=release()):shared.LegacySetsStorageTests.test_all_scores_filters_repeated_posts_and_solutions(self)
 def test_preserve_prior_versions_ids_attempt_and_idempotence(self):
  for p in sorted((ROOT/'content/questions').glob('*.v*.json')):
   if not (p.name.startswith('gel-a-algebra.v') and int(p.stem.rsplit('v',1)[1])>=3):apply_release(self.db,json.loads(p.read_text(encoding='utf-8')))
  rows=validate_release(release());attempt=self.repo.start_attempt(rows[0][0]['id'],'easy');old=copy.deepcopy(attempt)
  ids=[tuple(x) for x in self.db.execute('SELECT * FROM questions')];versions=[tuple(x) for x in self.db.execute('SELECT * FROM question_versions')]
  self.assertEqual(apply_release(self.db,release()),30);self.assertEqual(apply_release(self.db,release()),0)
  self.assertEqual(self.repo.attempt(attempt['id']),old);self.assertEqual([tuple(x) for x in self.db.execute('SELECT * FROM questions')],ids)
  for row in versions:self.assertEqual(tuple(self.db.execute('SELECT * FROM question_versions WHERE id=?',(row[0],)).fetchone()),row)
  report=coverage(self.db)
  for k,v in {'active_questions':1104,'with_learning_support':744,'first_pass_complete_units':108,'units_with_quiz':120,'remaining_units':217}.items():self.assertEqual(report[k],v)
 def test_stale_baseline_rolls_back_entire_release(self):
  r=release();r['entries'][-1]['expected_current']='00000000-0000-0000-0000-000000000000'
  before=[tuple(x) for x in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')]
  with self.assertRaises(ValueError):apply_release(self.db,r)
  self.assertEqual([tuple(x) for x in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')],before)
