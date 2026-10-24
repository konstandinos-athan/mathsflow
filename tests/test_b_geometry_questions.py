import copy,html,json,re,unittest
from collections import Counter
from unittest.mock import patch
from database import ROOT
from database.question_content import validate_release,apply_release
from database.question_coverage import coverage
from tests.support import DatabaseCase
from tests import test_question_content as shared

def release():
 return json.loads((ROOT/'content/questions/gym-b-geometry.v1.json').read_text(encoding='utf-8'))

class SecondGeometryValidationTests(unittest.TestCase):
 def test_units_objectives_difficulties_and_triangle_conditions(self):
  rows=validate_release(release());self.assertEqual(len(rows),84)
  self.assertEqual(len({u['id'] for u,_,_,_ in rows}),14)
  for uid in {u['id'] for u,_,_,_ in rows}:
   group=[(u,p) for u,_,_,p in rows if u['id']==uid]
   self.assertEqual(Counter(p['difficulty'] for _,p in group),{'easy':2,'medium':2,'hard':2})
   self.assertEqual({o for _,p in group for o in p['objective_ids']},{o['id'] for o in group[0][0]['learning_objectives']})
   self.assertTrue(all(p['exam_scope']==u['exam_scope'] for u,p in group))
  self.assertEqual(sum(len(p.get('geometry_cases',[])) for _,_,_,p in rows),13)

 def test_authored_scope_preserves_optional_recognition(self):
  rows=validate_release(release())
  for u,_,_,p in rows:
   if u['reference'] in ['4.4','4.6']:
    self.assertEqual(p['teaching_scope'],'optional')
    self.assertIn('χωρίς τύπους εμβαδού ή όγκου',p['practice_note'])
   if u['reference']=='3.2':self.assertIn('προαιρετικά',p['practice_note'])
  self.assertFalse(any('ημ²' in p['question'] or 'συν²' in p['question'] for _,_,_,p in rows))

 def test_rejects_bad_triangle_data_false_checks_and_wrong_answers(self):
  for mode in ['triangle','check','root','numeric','conceptual']:
   r=release()
   if mode=='triangle':next(e['payload'] for e in r['entries'] if 'geometry_cases' in e['payload'])['geometry_cases'][0]['sides']=[6,8,11]
   if mode=='check':next(e['payload'] for e in r['entries'] if 'checks' in e['payload'])['checks']=[['3*8','=','25']]
   if mode in ['root','numeric','conceptual']:
    kind={'root':'square_root','numeric':'numeric','conceptual':'conceptual'}[mode]
    p=next(e['payload'] for e in r['entries'] if e['payload']['verification']['kind']==kind);p['answer']=p['choices'][1]
   with self.subTest(mode=mode),self.assertRaises(ValueError):validate_release(r)

class SecondGeometryStorageTests(DatabaseCase):
 def test_all_new_quizzes_filters_scores_hints_and_solutions(self):
  with patch('tests.test_question_content.release',side_effect=release):
   shared.QuestionReleaseTests.test_all_new_quizzes_filters_scores_hints_and_solutions(self)

 def test_prior_banks_attempts_and_atomic_conflict_preserved(self):
  for name in ['gym-a-algebra','gym-a-geometry','gym-b-algebra']:
   apply_release(self.db,json.loads((ROOT/f'content/questions/{name}.v1.json').read_text(encoding='utf-8')))
  old=[tuple(r) for r in self.db.execute('SELECT * FROM question_versions')]
  uid=self.db.execute('SELECT unit_id FROM questions LIMIT 1').fetchone()[0];attempt=self.repo.start_attempt(uid,'easy')
  broken=release();broken['entries'][1]['expected_current']='stale'
  with self.assertRaises(ValueError):apply_release(self.db,broken)
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM question_versions').fetchone()[0],len(old))
  self.assertEqual(apply_release(self.db,release()),84);self.assertEqual(apply_release(self.db,release()),0)
  self.assertEqual(self.repo.attempt(attempt['id']),attempt)
  for row in old:self.assertEqual(tuple(self.db.execute('SELECT * FROM question_versions WHERE id=?',(row[0],)).fetchone()),row)
  report=coverage(self.db)
  for k,v in {'active_questions':948,'with_learning_support':468,'first_pass_complete_units':78,'units_with_quiz':94,'remaining_units':247}.items():self.assertEqual(report[k],v)

 def test_diagram_and_optional_notes_survive_submission_without_early_solutions(self):
  rows=validate_release(release());apply_release(self.db,release())
  for ref in ['2.1','3.2','4.4','4.6']:
   u=next(u for u,_,_,_ in rows if u['reference']==ref);url='/quiz/unit/'+u['id']
   page=self.client.get(url);text=html.unescape(page.get_data(as_text=True))
   self.assertNotIn('Πώς προκύπτει:',text);self.assertNotIn('Για τη δική σου επιλογή:',text)
   token=re.search(rb'name="attempt_token" value="([^"]+)"',page.data)[1].decode()
   after=html.unescape(self.client.post(url,data={'difficulty':'all','attempt_token':token}).get_data(as_text=True))
   if ref=='2.1':
    self.assertIn('gym-b-right-triangle.svg',text);self.assertIn('gym-b-right-triangle.svg',after)
    with self.client.get('/static/images/questions/gym-b-right-triangle.svg') as asset:self.assertEqual(asset.status_code,200)
   else:
    note=next(p['practice_note'] for unit,_,_,p in rows if unit['reference']==ref)
    self.assertIn(note,text);self.assertIn(note,after)
