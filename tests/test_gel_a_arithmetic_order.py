import copy,json,unittest
from collections import Counter
from unittest.mock import patch
from database import ROOT
from database.question_content import validate_release,apply_release
from database.question_coverage import coverage
from tests.support import DatabaseCase
from tests import test_gel_a_sets as shared

def release():return json.loads((ROOT/'content/questions/gel-a-algebra.v2.json').read_text(encoding='utf-8'))

class ArithmeticOrderValidationTests(unittest.TestCase):
 def test_sixty_revisions_have_full_support_and_original_difficulties(self):
  rows=validate_release(release());self.assertEqual(len(rows),60)
  for ref in ['2.1','2.2']:
   group=[(u,e,qid,p) for u,e,qid,p in rows if u['reference']==ref]
   self.assertEqual(len(group),30)
   self.assertEqual(Counter(p['difficulty'] for _,_,_,p in group),{'easy':10,'medium':10,'hard':10})
   self.assertEqual({x for _,_,_,p in group for x in p['objective_ids']},{o['id'] for o in group[0][0]['learning_objectives']})
   self.assertTrue(all(e['legacy_index']==i for i,(_,e,_,_) in enumerate(group,1)))

 def test_equivalent_power_options_and_interval_ambiguities_removed(self):
  self.assertEqual(2**6,4**3)
  q=next(e['payload'] for e in release()['entries'] if e['reference']=='2.1' and e['legacy_index']==16)
  self.assertEqual(q['answer'],'64');self.assertEqual(q['verification']['kind'],'numeric')
  r=release();p=next(e['payload'] for e in r['entries'] if e['reference']=='2.1' and e['legacy_index']==16);p['choices'][1]='64/1'
  with self.assertRaises(ValueError):validate_release(r)
  for i,answer in [(14,'1<x+3<7'),(15,'2<2x<10')]:
   p=next(e['payload'] for e in release()['entries'] if e['reference']=='2.2' and e['legacy_index']==i);self.assertEqual(p['answer'],answer)
  p=next(e['payload'] for e in release()['entries'] if e['reference']=='2.2' and e['legacy_index']==16)
  self.assertIn('ισοδύναμη',p['question']);self.assertNotIn('−1>−x>−5',p['choices'])

 def test_false_bounds_wrong_answers_and_excluded_proof_note(self):
  r=release();p=next(e['payload'] for e in r['entries'] if 'checks' in e['payload']);p['checks']=[['1/2','<','1/3']]
  with self.assertRaises(ValueError):validate_release(r)
  r=release();p=next(e['payload'] for e in r['entries'] if e['payload']['verification']['kind']=='numeric');p['answer']=p['choices'][1]
  with self.assertRaises(ValueError):validate_release(r)
  self.assertTrue(all('εξαιρούμενη απόδειξη' in e['payload']['practice_note'] for e in release()['entries'] if e['reference']=='2.2'))

class ArithmeticOrderStorageTests(DatabaseCase):
 def test_all_filters_scores_solutions_and_repeat_posts_for_both_units(self):
  for ref in ['2.1','2.2']:
   subset=release();subset['entries']=[e for e in subset['entries'] if e['reference']==ref]
   with patch('tests.test_gel_a_sets.release',return_value=subset):shared.LegacySetsStorageTests.test_all_scores_filters_repeated_posts_and_solutions(self)

 def test_all_previous_banks_ids_versions_attempts_and_other_pointers_preserved(self):
  for p in sorted((ROOT/'content/questions').glob('*.v*.json')):
   if p.name.startswith(('gym-','gel-a-algebra.')) and not (p.name.startswith('gel-a-algebra.v') and int(p.stem.rsplit('v',1)[1])>=2):apply_release(self.db,json.loads(p.read_text(encoding='utf-8')))
  rows=validate_release(release());uid=rows[0][0]['id'];attempt=self.repo.start_attempt(uid,'easy')
  old=copy.deepcopy(attempt);ids=[tuple(x) for x in self.db.execute('SELECT * FROM questions')]
  versions=[tuple(x) for x in self.db.execute('SELECT * FROM question_versions')]
  self.assertEqual(apply_release(self.db,release()),60);self.assertEqual(apply_release(self.db,release()),0)
  self.assertEqual(self.repo.attempt(attempt['id']),old)
  self.assertEqual([tuple(x) for x in self.db.execute('SELECT * FROM questions')],ids)
  for row in versions:self.assertEqual(tuple(self.db.execute('SELECT * FROM question_versions WHERE id=?',(row[0],)).fetchone()),row)
  report=coverage(self.db)
  for k,v in {'active_questions':1104,'with_learning_support':714,'first_pass_complete_units':107,'units_with_quiz':120,'remaining_units':218}.items():self.assertEqual(report[k],v)

 def test_conflict_in_second_unit_rolls_back_first_unit_too(self):
  r=release();r['entries'][30]['expected_current']='00000000-0000-0000-0000-000000000000'
  before=[tuple(x) for x in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')]
  with self.assertRaises(ValueError):apply_release(self.db,r)
  self.assertEqual([tuple(x) for x in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')],before)
