import copy,html,json,re,unittest
from collections import Counter
from database import ROOT
from database.question_content import validate_release,apply_release,deploy_releases
from tests.support import DatabaseCase
from database.question_coverage import coverage

def release():return json.loads((ROOT/'content/questions/gel-a-algebra.v1.json').read_text(encoding='utf-8'))

class LegacySetsValidationTests(unittest.TestCase):
 def test_all_thirty_existing_identities_support_and_levels(self):
  rows=validate_release(release());self.assertEqual(len(rows),30)
  self.assertEqual(len({u['id'] for u,_,_,_ in rows}),1)
  self.assertEqual(Counter(p['difficulty'] for _,_,_,p in rows),{'easy':10,'medium':10,'hard':10})
  self.assertEqual({x for _,_,_,p in rows for x in p['objective_ids']},{o['id'] for o in rows[0][0]['learning_objectives']})
  self.assertEqual(Counter(p['verification']['kind'] for _,_,_,p in rows),{'numeric':4,'finite_set':7,'conceptual':19})
  self.assertTrue(all(e['legacy_index']==i for i,(_,e,_,_) in enumerate(rows,1)))

 def test_finite_sets_reject_wrong_answers_equivalent_choices_and_bad_operands(self):
  for mode in ['answer','equivalent','bool','duplicate','operation','exclude']:
   r=release();p=next(e['payload'] for e in r['entries'] if e['legacy_index']==5)
   if mode=='answer':p['answer']=p['choices'][1]
   if mode=='equivalent':p['choices'][1]='{3,2,1}'
   if mode=='bool':p['verification']['left']=[True,2]
   if mode=='duplicate':p['verification']['left']=[1,1]
   if mode=='operation':p['verification']['operation']='__import__'
   if mode=='exclude':
    p=next(e['payload'] for e in r['entries'] if e['legacy_index']==22);p['verification']['exclude']=[3]
   with self.subTest(mode=mode),self.assertRaises(ValueError):validate_release(r)

 def test_legacy_index_key_course_and_baseline_are_bound(self):
  for mode in ['zero','large','bool','key','baseline','no_legacy_unit']:
   r=release();e=r['entries'][0]
   if mode=='zero':e['legacy_index']=0
   if mode=='large':e['legacy_index']=31
   if mode=='bool':e['legacy_index']=True
   if mode=='key':e['key']='core-01'
   if mode=='baseline':e['expected_current']=None
   if mode=='no_legacy_unit':r['course']='gym-c-geometry';e['reference']='1.1'
   with self.subTest(mode=mode),self.assertRaises(ValueError):validate_release(r)

 def test_ambiguous_question_revised_to_one_correct_choice(self):
  p=next(e['payload'] for e in release()['entries'] if e['legacy_index']==19)
  self.assertEqual(p['answer'],'{1}⊆{1,2}')
  reviews=p['verification']['choice_reviews'];self.assertEqual(sum(x['correct'] for x in reviews),1)
  self.assertEqual(next(x for x in reviews if x['choice']=='1∈{{1},2}')['correct'],False)
  self.assertFalse(1 in {frozenset({1}),2})

class LegacySetsStorageTests(DatabaseCase):
 def test_all_scores_filters_repeated_posts_and_solutions(self):
  r=release();apply_release(self.db,r);uid=validate_release(r)[0][0]['id']
  for level in ['all','easy','medium','hard']:
   for mode in ['correct','wrong','blank']:
    url='/quiz/unit/'+uid;page=self.client.get(url+'?difficulty='+level)
    token=re.search(rb'name="attempt_token" value="([^"]+)"',page.data)[1].decode()
    attempt=self.repo.attempt(self.signer.loads(token)['attempt_id']);self.assertEqual(attempt['total'],30 if level=='all' else 10)
    self.assertNotIn('Πώς προκύπτει:',page.get_data(as_text=True))
    form={'difficulty':level,'attempt_token':token}
    for i,q in enumerate(attempt['questions']):
     if mode!='blank':form[f'question_{i}']=q['answer'] if mode=='correct' else next(c for c in q['choices'] if c!=q['answer'])
    result=self.client.post(url,data=form);self.assertEqual(result.status_code,200)
    self.assertEqual(self.repo.attempt(attempt['id'])['score'],attempt['total'] if mode=='correct' else 0)
    text=html.unescape(result.get_data(as_text=True))
    for q in attempt['questions']:self.assertIn(q['solution'],text)
    self.assertEqual(self.client.post(url,data=form).data,result.data)
    for q in attempt['questions']:
     if 'image' in q:self.assertIn(q['image']['filename'],text)

 def test_old_attempt_and_all_original_question_identities_preserved(self):
  r=release();rows=validate_release(r);uid=rows[0][0]['id'];attempt=self.repo.start_attempt(uid,'easy')
  old=copy.deepcopy(attempt);identities=[tuple(x) for x in self.db.execute('SELECT * FROM questions')]
  versions=[tuple(x) for x in self.db.execute('SELECT * FROM question_versions')]
  self.assertEqual(apply_release(self.db,r),30);self.assertEqual(apply_release(self.db,r),0)
  self.assertEqual(self.repo.attempt(attempt['id']),old)
  self.assertEqual([tuple(x) for x in self.db.execute('SELECT * FROM questions')],identities)
  for row in versions:self.assertEqual(tuple(self.db.execute('SELECT * FROM question_versions WHERE id=?',(row[0],)).fetchone()),row)
  self.assertTrue(all(q['hint'] and q['solution'] for q in self.repo.start_attempt(uid,'easy')['questions']))

 def test_all_banks_deploy_twice_and_partial_coverage_is_honest(self):
  deploy_releases(self.db);versions=self.db.execute('SELECT COUNT(*) FROM question_versions').fetchone()[0]
  deploy_releases(self.db);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM question_versions').fetchone()[0],versions)
  report=coverage(self.db)
  gel=[u for u in report['units'] if u['course_key']=='gel-a-algebra']
  unit=next(u for u in gel if u['reference']=='Ε.2')
  self.assertEqual(unit['questions'],30);self.assertEqual(unit['with_learning_support'],30)
  self.assertTrue(unit['first_pass_complete'])

 def test_stale_baseline_rolls_back_every_revision(self):
  r=release();r['entries'][1]['expected_current']='00000000-0000-0000-0000-000000000000'
  pointers=[tuple(x) for x in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')]
  count=self.db.execute('SELECT COUNT(*) FROM question_versions').fetchone()[0]
  with self.assertRaises(ValueError):apply_release(self.db,r)
  self.assertEqual([tuple(x) for x in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')],pointers)
  self.assertEqual(self.db.execute('SELECT COUNT(*) FROM question_versions').fetchone()[0],count)
