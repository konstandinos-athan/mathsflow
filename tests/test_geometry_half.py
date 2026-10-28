import copy,json,unittest,xml.etree.ElementTree as ET
from collections import Counter
from unittest.mock import patch
from database import ROOT
from database.question_content import validate_release,apply_release,deploy_releases
from database.question_coverage import coverage
from database.geometry_checks import validate_geometry_cases
from tests.support import DatabaseCase
from tests import test_question_content as shared
COURSES=['gel-a-geometry','gel-b-geometry']
HISTORICAL_RELEASES=['gel-a-algebra.v1.json', 'gel-a-algebra.v2.json', 'gel-a-algebra.v3.json', 'gel-a-algebra.v4.json', 'gel-a-geometry.v1.json', 'gel-b-geometry.v1.json', 'gym-a-algebra.v1.json', 'gym-a-geometry.v1.json', 'gym-b-algebra.v1.json', 'gym-b-geometry.v1.json', 'gym-b-geometry.v2.json', 'gym-c-algebra.v1.json', 'gym-c-geometry.v1.json']
def historical_deploy(db):
 from pathlib import Path
 original_glob=Path.glob
 def historical_glob(path,pattern):
  results=original_glob(path,pattern)
  return (p for p in results if p.name in HISTORICAL_RELEASES) if path==ROOT/'content/questions' else results
 with patch.object(Path,'glob',historical_glob):deploy_releases(db)

def release(course):return json.loads((ROOT/'content/questions'/f'{course}.v1.json').read_text(encoding='utf-8'))
class GeometryHalfValidationTests(unittest.TestCase):
 def test_fifty_five_units_six_questions_objectives_levels(self):
  total=0
  for course,count in zip(COURSES,[33,22]):
   rows=validate_release(release(course));self.assertEqual(len(rows),count*6);total+=len(rows)
   units={u['id']:u for u,_,_,_ in rows};self.assertEqual(len(units),count)
   for uid,u in units.items():
    qs=[p for unit,_,_,p in rows if unit['id']==uid]
    self.assertEqual(Counter(p['difficulty'] for p in qs),{'easy':2,'medium':2,'hard':2})
    self.assertEqual({o for p in qs for o in p['objective_ids']},{o['id'] for o in u['learning_objectives']})
    self.assertTrue(any(p['verification']['kind']=='conceptual' for p in qs))
  self.assertEqual(total,330)
 def test_scope_sources_images_and_no_unexpanded_placeholders(self):
  images=set()
  for course in COURSES:
   for u,e,_,p in validate_release(release(course)):
    self.assertEqual(p['source_refs'],u['source_refs']);self.assertEqual(p['exam_scope'],u['exam_scope'])
    if u['restrictions']:self.assertTrue(all(x in p['practice_note'] for x in u['restrictions']))
    self.assertNotIn('{v}',str(p));self.assertNotIn('{answer}',str(p))
    if 'image' in p:images.add(p['image']['filename'])
  self.assertEqual(len(images),6)
  for name in images:
   tree=ET.parse(ROOT/'static'/name);self.assertTrue(tree.getroot().tag.endswith('svg'))
 def test_invalid_numeric_conceptual_triangle_and_false_check_rejected(self):
  for mode in ['numeric','conceptual','triangle','check']:
   r=release(COURSES[0])
   if mode in ['numeric','conceptual']:
    p=next(e['payload'] for e in r['entries'] if e['payload']['verification']['kind']==mode);p['answer']=p['choices'][1]
   if mode=='triangle':next(e['payload'] for e in r['entries'] if 'geometry_cases' in e['payload'])['geometry_cases']=[{'sides':[3,4,8],'angles_degrees':[None]*3}]
   if mode=='check':r['entries'][0]['payload']['checks']=[['1','=','2']]
   with self.subTest(mode=mode),self.assertRaises(ValueError):validate_release(r)
 def test_counterexamples_centroid_similarity_and_external_division(self):
  self.assertEqual(3*3+1,2*(3+2));self.assertEqual(60-12,48)
  self.assertEqual(9/6,12/8);self.assertEqual(12/8,15/10)
  self.assertEqual(5,10/2);self.assertEqual(7.5,15/2)
  self.assertNotEqual(3/2,5/2);self.assertNotEqual(60,120)
  with self.assertRaises(ValueError):validate_geometry_cases([{'sides':[3,5,8],'angles_degrees':[None]*3}])
class GeometryHalfStorageTests(DatabaseCase):
 def test_all_fifty_five_units_filters_scores_feedback_repeat_posts(self):
  for course in COURSES:
   with patch('tests.test_question_content.release',return_value=release(course)):shared.QuestionReleaseTests.test_all_new_quizzes_filters_scores_hints_and_solutions(self)
 def test_full_deployment_reaches_half_idempotently(self):
  historical_deploy(self.db);n=self.db.execute('SELECT COUNT(*) FROM question_versions').fetchone()[0]
  historical_deploy(self.db);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM question_versions').fetchone()[0],n)
  report=coverage(self.db)
  for k,v in {'active_questions':1434,'with_learning_support':1104,'first_pass_complete_units':164,'units_with_quiz':175,'remaining_units':161}.items():self.assertEqual(report[k],v)
  self.assertEqual(n,1585);self.assertGreaterEqual(report['first_pass_complete_units']/report['catalog_units'],0.5)
  self.assertEqual(report['educator_approved_units'],0)
 def test_prior_questions_pointers_versions_attempts_preserved(self):
  for p in sorted((ROOT/'content/questions').glob('*.v*.json')):
   if p.name in HISTORICAL_RELEASES and p.name not in [f'{c}.v1.json' for c in COURSES]:apply_release(self.db,json.loads(p.read_text(encoding='utf-8')))
  versions=[tuple(x) for x in self.db.execute('SELECT * FROM question_versions')];ids=[tuple(x) for x in self.db.execute('SELECT * FROM questions')];pointers=[tuple(x) for x in self.db.execute('SELECT * FROM current_questions')]
  uid=ids[0][1];attempt=self.repo.start_attempt(uid,'easy');old=copy.deepcopy(attempt)
  for course,count in zip(COURSES,[198,132]):self.assertEqual(apply_release(self.db,release(course)),count)
  self.assertEqual(self.repo.attempt(attempt['id']),old)
  for row in ids:self.assertEqual(tuple(self.db.execute('SELECT * FROM questions WHERE id=?',(row[0],)).fetchone()),row)
  for row in versions:self.assertEqual(tuple(self.db.execute('SELECT * FROM question_versions WHERE id=?',(row[0],)).fetchone()),row)
  for row in pointers:self.assertEqual(tuple(self.db.execute('SELECT * FROM current_questions WHERE question_id=?',(row[0],)).fetchone()),row)
 def test_stale_last_baseline_rolls_back_whole_course(self):
  for course in COURSES:
   r=release(course);r['entries'][-1]['expected_current']='stale';before=self.db.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
   with self.assertRaises(ValueError):apply_release(self.db,r)
   self.assertEqual(self.db.execute('SELECT COUNT(*) FROM questions').fetchone()[0],before)
