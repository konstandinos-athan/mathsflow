import copy,html,json,re,unittest
from collections import Counter
from unittest.mock import patch
from database import ROOT
from database.question_content import validate_release,apply_release
from database.question_coverage import coverage
from tests.support import DatabaseCase
from tests import test_question_content as shared


def release():
    return json.loads((ROOT/'content/questions/gym-b-algebra.v1.json').read_text(encoding='utf-8'))


class SecondAlgebraValidationTests(unittest.TestCase):
    def test_all_units_objectives_and_difficulties(self):
        rows=validate_release(release());self.assertEqual(len(rows),102)
        self.assertEqual(len({u['id'] for u,_,_,_ in rows}),17)
        for uid in {u['id'] for u,_,_,_ in rows}:
            group=[(u,p) for u,_,_,p in rows if u['id']==uid]
            self.assertEqual(Counter(p['difficulty'] for _,p in group),{'easy':2,'medium':2,'hard':2})
            self.assertEqual({o for _,p in group for o in p['objective_ids']},{o['id'] for o in group[0][0]['learning_objectives']})
            self.assertTrue(all(p['exam_scope']==u['exam_scope'] for u,p in group))

    def test_square_root_rejects_negative_or_wrong_answers_and_radicands(self):
        base=release();e=next(e for e in base['entries'] if e['reference']=='2.1' and e['key']=='core-01')
        for mode in ['negative_answer','wrong_answer','negative_radicand','call']:
            item=copy.deepcopy(e);p=item['payload']
            if mode=='negative_answer':p['answer']='−7'
            if mode=='wrong_answer':p['answer']='14'
            if mode=='negative_radicand':p['verification']['radicand']='-49'
            if mode=='call':p['verification']['radicand']='__import__("os")'
            with self.subTest(mode=mode),self.assertRaises(ValueError):validate_release({**base,'entries':[item]})

    def test_zero_and_fractional_square_roots_are_exact(self):
        rows=validate_release(release())
        roots=[p for _,_,_,p in rows if p['verification']['kind']=='square_root']
        self.assertTrue(any(p['answer']=='0' for p in roots))
        self.assertTrue(any(p['answer']=='3/4' for p in roots))
        self.assertEqual(sum(len(p.get('geometry_cases',[])) for _,_,_,p in rows),2)

    def test_scope_and_non_exam_notes_are_required_by_authored_bank(self):
        rows=validate_release(release())
        for u,_,_,p in rows:
            if u['reference'] in ['7.7','7.8','7.9']:
                self.assertEqual(p['exam_scope'],'excluded_bridge')
                self.assertIn('δεν αποτελεί εξεταστέα ύλη',p['practice_note'])
            if u['reference']=='4.1':self.assertIn('δεν εξετάζονται ως θεωρία',p['practice_note'])
        base=release();base['entries'][0]['payload']['exam_scope']='school_specific_not_preselected'
        with self.assertRaises(ValueError):validate_release(base)

    def test_bad_images_notes_and_false_arithmetic_bounds_are_rejected(self):
        base=release()
        for mode in ['traversal','missing_file','missing_alt','bad_note','false_bound']:
            r=copy.deepcopy(base)
            image=next(e for e in r['entries'] if 'image' in e['payload'])['payload']['image']
            if mode=='traversal':image['filename']='images/questions/../../other.svg'
            if mode=='missing_file':image['filename']='images/questions/does-not-exist.svg'
            if mode=='missing_alt':image['alt']=''
            if mode=='bad_note':r['entries'][0]['payload']['practice_note']='<script>invalid note</script>'
            if mode=='false_bound':next(e for e in r['entries'] if 'checks' in e['payload'])['payload']['checks']=[['36','<','30']]
            with self.subTest(mode=mode),self.assertRaises(ValueError):validate_release(r)


class SecondAlgebraStorageTests(DatabaseCase):
    def test_all_new_quizzes_filters_scores_hints_and_solutions(self):
        with patch('tests.test_question_content.release',side_effect=release):
            shared.QuestionReleaseTests.test_all_new_quizzes_filters_scores_hints_and_solutions(self)

    def test_existing_banks_and_attempts_preserved(self):
        for filename in ['gym-a-algebra.v1.json','gym-a-geometry.v1.json']:
            apply_release(self.db,json.loads((ROOT/'content/questions'/filename).read_text(encoding='utf-8')))
        versions=[tuple(r) for r in self.db.execute('SELECT * FROM question_versions')]
        uid=self.db.execute('SELECT unit_id FROM questions LIMIT 1').fetchone()[0]
        attempt=self.repo.start_attempt(uid,'easy')
        self.assertEqual(apply_release(self.db,release()),102)
        self.assertEqual(apply_release(self.db,release()),0)
        self.assertEqual(self.repo.attempt(attempt['id']),attempt)
        for row in versions:self.assertEqual(tuple(self.db.execute('SELECT * FROM question_versions WHERE id=?',(row[0],)).fetchone()),row)
        report=coverage(self.db)
        self.assertEqual(report['active_questions'],864)
        self.assertEqual(report['first_pass_complete_units'],64)
        self.assertEqual(report['units_with_quiz'],80)
        self.assertEqual(report['remaining_units'],261)

    def test_non_exam_notes_and_chart_survive_submission(self):
        rows=validate_release(release());apply_release(self.db,release())
        for ref in ['7.7','7.8','7.9','4.1','4.2']:
            unit=next(u for u,_,_,_ in rows if u['reference']==ref)
            url='/quiz/unit/'+unit['id'];page=self.client.get(url)
            if ref=='4.2':self.assertIn('gym-b-travel-bars.svg',page.get_data(as_text=True))
            else:self.assertIn('δεν '.encode(),page.data)
            token=re.search(rb'name="attempt_token" value="([^"]+)"',page.data)[1].decode()
            result=self.client.post(url,data={'difficulty':'all','attempt_token':token})
            self.assertEqual(result.status_code,200)
            if ref=='4.2':self.assertIn('gym-b-travel-bars.svg',result.get_data(as_text=True))
            else:
                q=next(p for u,_,_,p in rows if u['reference']==ref)
                self.assertIn(q['practice_note'],html.unescape(result.get_data(as_text=True)))
