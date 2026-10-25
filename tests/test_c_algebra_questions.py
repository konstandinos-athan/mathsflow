import copy,html,json,re,unittest
from collections import Counter
from unittest.mock import patch
from database import ROOT
from database.question_content import validate_release,apply_release,deploy_releases
from database.question_coverage import coverage
from tests.support import DatabaseCase
from tests import test_question_content as shared

def release():return json.loads((ROOT/'content/questions/gym-c-algebra.v1.json').read_text(encoding='utf-8'))

class ThirdAlgebraValidationTests(unittest.TestCase):
 def test_units_objectives_and_difficulties(self):
  rows=validate_release(release());self.assertEqual(len(rows),114);self.assertEqual(len({u['id'] for u,_,_,_ in rows}),19)
  for uid in {u['id'] for u,_,_,_ in rows}:
   group=[(u,p) for u,_,_,p in rows if u['id']==uid]
   self.assertEqual(Counter(p['difficulty'] for _,p in group),{'easy':2,'medium':2,'hard':2})
   self.assertEqual({o for _,p in group for o in p['objective_ids']},{o['id'] for o in group[0][0]['learning_objectives']})
   self.assertTrue(all(p['exam_scope']==u['exam_scope'] for u,p in group))

 def test_authored_optional_scope_and_exclusions(self):
  rows=validate_release(release())
  for u,_,_,p in rows:
   if u['reference']=='2.1':
    self.assertEqual(p['teaching_scope'],'optional');self.assertIn('Προαιρετική',p['practice_note'])
   if u['reference']=='1.8':self.assertIn('ΜΚΔ',p['practice_note'])
   if u['reference']=='2.2':self.assertIn('απόδειξη',p['practice_note'])
  self.assertEqual(len([p for _,_,_,p in rows if 'image' in p]),2)

 def test_wrong_answers_false_assertions_and_image_paths_rejected(self):
  for mode in ['numeric','square_root','conceptual','check','image']:
   r=release()
   if mode in ['numeric','square_root','conceptual']:
    p=next(e['payload'] for e in r['entries'] if e['payload']['verification']['kind']==mode);p['answer']=p['choices'][1]
   if mode=='check':next(e['payload'] for e in r['entries'] if 'checks' in e['payload'])['checks']=[['1','=','2']]
   if mode=='image':next(e['payload'] for e in r['entries'] if 'image' in e['payload'])['image']['filename']='images/questions/../../bad.svg'
   with self.subTest(mode=mode),self.assertRaises(ValueError):validate_release(r)

class ThirdAlgebraStorageTests(DatabaseCase):
 def test_all_new_quizzes_filters_scores_hints_and_solutions(self):
  with patch('tests.test_question_content.release',side_effect=release):shared.QuestionReleaseTests.test_all_new_quizzes_filters_scores_hints_and_solutions(self)

 def test_prior_banks_and_attempts_preserved_with_atomic_conflict(self):
  for filename in ['gym-a-algebra.v1.json','gym-a-geometry.v1.json','gym-b-algebra.v1.json','gym-b-geometry.v1.json','gym-b-geometry.v2.json']:
   apply_release(self.db,json.loads((ROOT/'content/questions'/filename).read_text(encoding='utf-8')))
  old=[tuple(x) for x in self.db.execute('SELECT * FROM question_versions')]
  uid=self.db.execute('SELECT unit_id FROM questions LIMIT 1').fetchone()[0];attempt=self.repo.start_attempt(uid,'easy')
  r=release();r['entries'][1]['expected_current']='stale'
  with self.assertRaises(ValueError):apply_release(self.db,r)
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM question_versions').fetchone()[0],len(old))
  self.assertEqual(apply_release(self.db,release()),114);self.assertEqual(apply_release(self.db,release()),0)
  self.assertEqual(self.repo.attempt(attempt['id']),attempt)
  for row in old:self.assertEqual(tuple(self.db.execute('SELECT * FROM question_versions WHERE id=?',(row[0],)).fetchone()),row)
  report=coverage(self.db)
  for k,v in {'active_questions':1062,'with_learning_support':582,'first_pass_complete_units':97,'units_with_quiz':113,'remaining_units':228}.items():self.assertEqual(report[k],v)

 def test_figures_and_scope_notes_survive_submission_without_early_feedback(self):
  rows=validate_release(release());apply_release(self.db,release())
  for ref in ['1.3','1.4','1.8','2.1','2.2','2.5','3.2']:
   u=next(u for u,_,_,_ in rows if u['reference']==ref);url='/quiz/unit/'+u['id']
   page=self.client.get(url);text=html.unescape(page.get_data(as_text=True))
   self.assertNotIn('Πώς προκύπτει:',text);self.assertNotIn('Για τη δική σου επιλογή:',text)
   token=re.search(rb'name="attempt_token" value="([^"]+)"',page.data)[1].decode()
   after=html.unescape(self.client.post(url,data={'difficulty':'all','attempt_token':token}).get_data(as_text=True))
   if ref in ['1.4','3.2']:
    image=next(p['image'] for unit,_,_,p in rows if unit['reference']==ref and 'image' in p)
    self.assertIn(image['filename'],text);self.assertIn(image['filename'],after)
    with self.client.get('/static/'+image['filename']) as asset:self.assertEqual(asset.status_code,200)
   else:
    note=next(p['practice_note'] for unit,_,_,p in rows if unit['reference']==ref)
    self.assertIn(note,text);self.assertIn(note,after)
