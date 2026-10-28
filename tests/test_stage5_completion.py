import copy,html,json,re,unittest
from collections import Counter
from fractions import Fraction
from database import ROOT
from database.question_content import validate_release,apply_release,deploy_releases,number
from database.question_coverage import coverage
from tests.support import DatabaseCase
NAMES=['epal-a-algebra.v1.json', 'epal-a-algebra.v2.json', 'epal-a-geometry.v1.json', 'epal-b-algebra.v1.json', 'epal-b-geometry.v1.json', 'epal-c-algebra.v1.json', 'epal-c-geometry.v1.json', 'gel-a-algebra.v5.json', 'gel-b-algebra.v1.json', 'gel-b-orientation.v1.json', 'gel-c-general.v1.json', 'gel-c-orientation.v1.json']
PRIOR=['gel-a-algebra.v1.json', 'gel-a-algebra.v2.json', 'gel-a-algebra.v3.json', 'gel-a-algebra.v4.json', 'gel-a-geometry.v1.json', 'gel-b-geometry.v1.json', 'gym-a-algebra.v1.json', 'gym-a-geometry.v1.json', 'gym-b-algebra.v1.json', 'gym-b-geometry.v1.json', 'gym-b-geometry.v2.json', 'gym-c-algebra.v1.json', 'gym-c-geometry.v1.json']
def release(name):return json.loads((ROOT/'content/questions'/name).read_text(encoding='utf-8'))
def prior(db):
 for name in PRIOR:apply_release(db,release(name))
class CompletionValidationTests(unittest.TestCase):
 def test_all_161_units_provenance_levels_and_objectives(self):
  by_unit={};total=0
  for name in NAMES:
   for u,e,qid,p in validate_release(release(name)):
    by_unit.setdefault(u['id'],[]).append((u,p));total+=1
    self.assertEqual(p['source_refs'],u['source_refs']);self.assertEqual(p['exam_scope'],u['exam_scope'])
    for restriction in u['restrictions']:self.assertIn(restriction,p['practice_note'])
    self.assertNotRegex(json.dumps(p,ensure_ascii=False),r'\{(?:v|answer)\}')
  self.assertEqual(total,1614);self.assertEqual(len(by_unit),161)
  for uid,rows in by_unit.items():
   levels=Counter(p['difficulty'] for _,p in rows)
   self.assertTrue(all(levels[x]>=2 for x in ['easy','medium','hard']))
   self.assertEqual({oid for _,p in rows for oid in p['objective_ids']},{o['id'] for o in rows[0][0]['learning_objectives']})
 def test_epal_specific_scope_differences(self):
  es=[e['payload'] for e in release('epal-b-geometry.v1.json')['entries'] if e['reference']=='7.6']
  self.assertEqual(sum(p['verification']['kind']=='conceptual' for p in es),4)
  self.assertTrue(all('μόνο οι ορισμοί' in p['practice_note'] for p in es))
  heron=[e['payload'] for e in release('epal-c-geometry.v1.json')['entries'] if e['reference']=='10.4']
  self.assertEqual(sum(p['verification']['kind']=='square_root' for p in heron),2)
  for p in heron:self.assertNotRegex(p['question'],r'ημίτονο|ημ[θΑΒΓ(]')
  for e in release('epal-b-algebra.v1.json')['entries']:
   if e['reference'] in ['5.1','5.3']:self.assertNotIn('Λύσε',e['payload']['question'])
  for e in release('epal-a-algebra.v2.json')['entries']:
   if e['reference']=='6.2':self.assertNotIn('απόσταση',e['payload']['question'])
 def test_330_legacy_revisions_have_identity_and_baseline(self):
  entries=release('gel-a-algebra.v5.json')['entries'];self.assertEqual(len(entries),330)
  for e in entries:self.assertTrue(e['expected_current']);self.assertEqual(e['key'],f"legacy-{e['legacy_index']:02}")
  for ref in {e['reference'] for e in entries}:
   subset=[e for e in entries if e['reference']==ref]
   self.assertEqual({e['legacy_index'] for e in subset},set(range(1,31)))
   self.assertEqual(Counter(e['payload']['difficulty'] for e in subset),{'easy':10,'medium':10,'hard':10})
 def test_invalid_answer_duplicate_numeric_and_review_rejected(self):
  for name in NAMES:
   for mode in ['answer','duplicate','review']:
    r=copy.deepcopy(release(name));p=next(e['payload'] for e in r['entries'] if e['payload']['verification']['kind']=='numeric')
    if mode=='answer':p['answer']=p['choices'][1]
    if mode=='duplicate':p['choices'][1]=p['choices'][0]
    if mode=='review':p['educator_review']='approved'
    with self.subTest(name=name,mode=mode),self.assertRaises(ValueError):validate_release(r)
 def test_integer_inequality_answers_by_enumerating_actual_domain(self):
  r=release('gel-a-algebra.v5.json')
  groups={ref:[e['payload'] for e in r['entries'] if e['reference']==ref] for ref in ['4.1','4.2']}
  for j,v in enumerate(range(2,7)):
   self.assertEqual(number(groups['4.2'][j]['answer']),sum(x*x<v*v for x in range(-20,21)))
   self.assertEqual(number(groups['4.2'][5+j]['answer']),sum(x*x<=v*v for x in range(-20,21)))
   self.assertEqual(number(groups['4.2'][10+j]['answer']),sum((x-1)*(x-v-2)<0 for x in range(-20,21)))
   self.assertEqual(number(groups['4.1'][15+j]['answer']),sum(0<=x<v for x in range(-20,21)))
  for j,v in enumerate(range(2,6)):
   self.assertEqual(number(groups['4.2'][20+j]['answer']),sum(-(x-1)*(x-v-2)>=0 for x in range(v+4)))
   self.assertEqual(number(groups['4.1'][20+j]['answer']),sum(x>1 and 2*x<=2*v+4 for x in range(-20,21)))
 def test_progression_answers_by_explicit_terms(self):
  r=release('gel-a-algebra.v5.json')
  for ref in ['5.2','5.3']:
   es=[e['payload'] for e in r['entries'] if e['reference']==ref]
   for j,v in enumerate(range(2,6)):
    if ref=='5.2':expected=sum(5*v-2*k for k in range(v));q=es[24+j]
    else:expected=sum(2*2**k for k in range(v));q=es[20+j]
    self.assertEqual(number(q['answer']),expected)
 def test_heron_and_geometry_counterexamples(self):
  es=[e['payload'] for e in release('epal-c-geometry.v1.json')['entries'] if e['reference']=='10.4']
  for q,sides in zip(es[2:4],[(5,5,6),(13,14,15)]):
   s=Fraction(sum(sides),2);area2=s
   for a in sides:area2*=s-a
   self.assertEqual(number(q['answer'])**2,area2)
  self.assertEqual(1,1**2)
class CompletionStorageTests(DatabaseCase):
 def test_all_325_units_deploy_idempotently(self):
  deploy_releases(self.db);n=self.db.execute('SELECT COUNT(*) FROM question_versions').fetchone()[0]
  deploy_releases(self.db);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM question_versions').fetchone()[0],n)
  report=coverage(self.db)
  for key,value in {'catalog_units':325,'units_with_quiz':325,'active_questions':2718,'with_learning_support':2718,'first_pass_complete_units':325,'remaining_units':0,'educator_approved_units':0}.items():self.assertEqual(report[key],value)
  self.assertEqual(n,3199);self.assertEqual(report['legacy_quality_issues'],[])
 def test_all_161_units_filters_scores_solutions_and_repeat_posts(self):
  deploy_releases(self.db)
  units={u['id']:u for name in NAMES for u,_,_,_ in validate_release(release(name))}
  for uid,unit in units.items():
   total=self.db.execute('SELECT COUNT(*) FROM questions WHERE unit_id=?',(uid,)).fetchone()[0]
   for level in ['all','easy','medium','hard']:
    for mode in ['correct','wrong','blank']:
     with self.subTest(unit=uid,level=level,mode=mode):
      url='/quiz/unit/'+uid;response=self.client.get(url+'?difficulty='+level);self.assertEqual(response.status_code,200)
      token=re.search(rb'name="attempt_token" value="([^"]+)"',response.data)[1].decode()
      attempt=self.repo.attempt(self.signer.loads(token)['attempt_id']);self.assertEqual(attempt['total'],total if level=='all' else total//3)
      self.assertEqual(response.data.count(b'class="quiz-hint"'),attempt['total']);self.assertNotIn('Πώς προκύπτει:'.encode(),response.data)
      form={'attempt_token':token,'difficulty':level}
      for i,q in enumerate(attempt['questions']):
       if mode!='blank':form[f'question_{i}']=q['answer'] if mode=='correct' else next(c for c in q['choices'] if c!=q['answer'])
      result=self.client.post(url,data=form);self.assertEqual(result.status_code,200)
      self.assertEqual(self.repo.attempt(attempt['id'])['score'],attempt['total'] if mode=='correct' else 0)
      for q in attempt['questions']:self.assertIn(q['solution'],html.unescape(result.get_data(as_text=True)))
      self.assertEqual(self.client.post(url,data=form).data,result.data)
 def test_preserve_all_old_ids_versions_and_open_legacy_attempt(self):
  prior(self.db);r=release('gel-a-algebra.v5.json');uid=validate_release(r)[0][0]['id'];attempt=copy.deepcopy(self.repo.start_attempt(uid,'easy'))
  old={t:[dict(x) for x in self.db.execute('SELECT * FROM '+t)] for t in ['questions','question_versions','current_questions']}
  changed={qid for _,_,qid,_ in validate_release(r)}
  deploy_releases(self.db);self.assertEqual(self.repo.attempt(attempt['id']),attempt)
  for t,key in [('questions','id'),('question_versions','id'),('current_questions','question_id')]:
   for row in old[t]:
    if t=='current_questions' and row[key] in changed:continue
    self.assertEqual(dict(self.db.execute('SELECT * FROM '+t+' WHERE '+key+'=?',(row[key],)).fetchone()),row)
 def test_last_entry_conflict_rolls_back_every_release(self):
  prior(self.db)
  for name in NAMES:
   r=copy.deepcopy(release(name));r['entries'][-1]['expected_current']='00000000-0000-0000-0000-000000000000'
   counts=tuple(self.db.execute('SELECT (SELECT COUNT(*) FROM questions),(SELECT COUNT(*) FROM question_versions)').fetchone())
   pointers=[tuple(x) for x in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')]
   with self.subTest(name=name),self.assertRaises(ValueError):apply_release(self.db,r)
   self.assertEqual(tuple(self.db.execute('SELECT (SELECT COUNT(*) FROM questions),(SELECT COUNT(*) FROM question_versions)').fetchone()),counts)
   self.assertEqual([tuple(x) for x in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')],pointers)
