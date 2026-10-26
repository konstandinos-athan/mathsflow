import copy,json,unittest
from unittest.mock import patch
from database import ROOT
from database.question_content import validate_release,apply_release
from database.question_coverage import coverage
from tests.support import DatabaseCase
from tests import test_gel_a_sets as shared
def release():return json.loads((ROOT/'content/questions/gel-a-algebra.v4.json').read_text(encoding='utf-8'))
class RootsValidationTests(unittest.TestCase):
 def test_scope_difficulties_objectives_and_rational_exponents(self):
  from collections import Counter
  rows=validate_release(release());self.assertEqual(len(rows),30)
  self.assertEqual(Counter(p['difficulty'] for _,_,_,p in rows),{'easy':10,'medium':10,'hard':10})
  self.assertEqual({x for _,_,_,p in rows for x in p['objective_ids']},{o['id'] for o in rows[0][0]['learning_objectives']})
  self.assertTrue(all('ιδιότητες 3 και 4' in p['practice_note'] for _,_,_,p in rows))
  for i,answer in [(13,'9'),(21,'8'),(22,'1/9'),(28,'2')]:self.assertEqual(release()['entries'][i-1]['payload']['answer'],answer)
 def test_equivalent_old_choices_removed_and_negative_sign_explicit(self):
  q=release()['entries'][25]['payload'];self.assertEqual(q['answer'],'3');self.assertEqual(q['verification']['kind'],'numeric')
  q=release()['entries'][28]['payload'];self.assertEqual(q['answer'],'−α');self.assertNotIn('∣α∣',q['choices'])
  for a in [-1,-2,-3,-10]:self.assertEqual(abs(a),-a)
  self.assertEqual(3**2,9);self.assertEqual(3**4,81);self.assertEqual(2**3,8)
  from fractions import Fraction as F
  for i,choices,squares in [(18,['√2/2','√2','2√2','1/2'],[F(1,2),F(2),F(8),F(1,4)]),(27,['2√3/3','√3/2','2√3','3√3/2'],[F(4,3),F(3,4),F(12),F(27,4)])]:
   self.assertEqual(release()['entries'][i-1]['payload']['choices'],choices)
   self.assertEqual(len(set(squares)),4)

 def test_negative_root_wrong_answer_and_equivalent_numbers_rejected(self):
  for mutation in ['negative','wrong','equivalent']:
   r=release();p=r['entries'][0]['payload']
   if mutation=='negative':p['verification']['radicand']='-9'
   elif mutation=='wrong':p['answer']='−3'
   else:p['choices'][1]='3/1'
   with self.assertRaises(ValueError):validate_release(r)
class RootsStorageTests(DatabaseCase):
 def test_filters_all_scores_feedback_repeat_posts(self):
  with patch('tests.test_gel_a_sets.release',return_value=release()):shared.LegacySetsStorageTests.test_all_scores_filters_repeated_posts_and_solutions(self)
 def test_preserve_prior_versions_ids_attempt_and_idempotence(self):
  for p in sorted((ROOT/'content/questions').glob('*.v*.json')):
   if p.name.startswith(('gym-','gel-a-algebra.')) and not (p.name.startswith('gel-a-algebra.v') and int(p.stem.rsplit('v',1)[1])>=4):apply_release(self.db,json.loads(p.read_text(encoding='utf-8')))
  rows=validate_release(release());attempt=self.repo.start_attempt(rows[0][0]['id'],'easy');old=copy.deepcopy(attempt)
  ids=[tuple(x) for x in self.db.execute('SELECT * FROM questions')];versions=[tuple(x) for x in self.db.execute('SELECT * FROM question_versions')]
  self.assertEqual(apply_release(self.db,release()),30);self.assertEqual(apply_release(self.db,release()),0)
  self.assertEqual(self.repo.attempt(attempt['id']),old);self.assertEqual([tuple(x) for x in self.db.execute('SELECT * FROM questions')],ids)
  for row in versions:self.assertEqual(tuple(self.db.execute('SELECT * FROM question_versions WHERE id=?',(row[0],)).fetchone()),row)
  report=coverage(self.db)
  for k,v in {'active_questions':1104,'with_learning_support':774,'first_pass_complete_units':109,'units_with_quiz':120,'remaining_units':216}.items():self.assertEqual(report[k],v)
 def test_stale_baseline_rolls_back_entire_release(self):
  r=release();r['entries'][-1]['expected_current']='00000000-0000-0000-0000-000000000000'
  before=[tuple(x) for x in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')]
  with self.assertRaises(ValueError):apply_release(self.db,r)
  self.assertEqual([tuple(x) for x in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')],before)
