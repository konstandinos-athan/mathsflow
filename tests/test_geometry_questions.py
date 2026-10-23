import copy
import json
import html
import re
import unittest
from collections import Counter
from unittest.mock import patch
from database import ROOT
from database.question_content import validate_release, apply_release, deploy_releases
from database.question_coverage import coverage
from tests.support import DatabaseCase
from tests import test_question_content as question_tests


def geometry_release():
    return json.loads((ROOT/'content/questions/gym-a-geometry.v1.json').read_text(encoding='utf-8'))


class GeometryBankValidationTests(unittest.TestCase):
    def test_geometry_bank_coverage_and_reviewed_choices(self):
        prepared=validate_release(geometry_release())
        self.assertEqual(len(prepared),138)
        self.assertEqual(len({u['id'] for u,_,_,_ in prepared}),23)
        self.assertGreater(sum(p['verification']['kind']=='conceptual' for _,_,_,p in prepared),40)
        self.assertEqual(sum(len(p.get('geometry_cases',[])) for _,_,_,p in prepared),7)
        for uid in {u['id'] for u,_,_,_ in prepared}:
            rows=[(u,p) for u,_,_,p in prepared if u['id']==uid]
            self.assertEqual(Counter(p['difficulty'] for _,p in rows),{'easy':2,'medium':2,'hard':2})
            self.assertEqual({x for _,p in rows for x in p['objective_ids']},{o['id'] for o in rows[0][0]['learning_objectives']})

    def test_conceptual_items_require_one_answer_and_all_reasons(self):
        base=geometry_release()
        entry=next(e for e in base['entries'] if e['payload']['verification']['kind']=='conceptual')
        mutations=[lambda p:p['verification']['choice_reviews'][1].update(correct=True),
                   lambda p:p['verification']['choice_reviews'][0].update(correct=False),
                   lambda p:p['verification']['choice_reviews'][2].update(reason=''),
                   lambda p:p['verification']['choice_reviews'][3].update(choice='foreign choice'),
                   lambda p:p['verification']['choice_reviews'][2].update(reason='<script>invalid markup</script>'),
                   lambda p:p['verification']['choice_reviews'][2].update(reason='Unbalanced math \\(1+2'),
                   lambda p:p.update(answer=p['choices'][1]),
                   lambda p:p['verification']['choice_reviews'].pop()]
        for mutate in mutations:
            item=copy.deepcopy(entry);mutate(item['payload'])
            with self.assertRaises(ValueError):validate_release({**base,'entries':[item]})

    def test_impossible_geometry_is_rejected_on_both_question_types(self):
        base=geometry_release()
        for kind in ['numeric','conceptual']:
            entry=copy.deepcopy(next(e for e in base['entries'] if e['payload']['verification']['kind']==kind))
            entry['payload']['geometry_cases']=[{'sides':[2,3,8],'angles_degrees':[None,None,None]}]
            with self.assertRaises(ValueError):validate_release({**base,'entries':[entry]})

    def test_optional_units_and_scope_are_not_silently_promoted(self):
        rows=validate_release(geometry_release())
        optional={u['reference'] for u,_,_,p in rows if p['teaching_scope']=='optional'}
        self.assertEqual(optional,{'1.12','1.13','3.4'})
        altered=geometry_release();altered['entries'][0]['payload']['teaching_scope']='required'
        with self.assertRaises(ValueError):validate_release(altered)


class GeometryBankStorageTests(DatabaseCase):
    def test_selected_distractor_feedback_is_shown_only_after_submission(self):
        r=geometry_release();apply_release(self.db,r)
        unit=validate_release(r)[0][0]
        response=self.client.get('/quiz/unit/'+unit['id'])
        self.assertNotIn('Για τη δική σου επιλογή:'.encode(),response.data)
        token=re.search(rb'name="attempt_token" value="([^"]+)"',response.data)[1].decode()
        attempt=self.repo.attempt(self.signer.loads(token)['attempt_id'])
        index=next(i for i,q in enumerate(attempt['questions']) if q['verification']['kind']=='conceptual')
        question=attempt['questions'][index]
        review=next(r for r in question['verification']['choice_reviews'] if not r['correct'])
        response=self.client.post('/quiz/unit/'+unit['id'],data={'difficulty':'all','attempt_token':token,f'question_{index}':review['choice']})
        self.assertIn('Για τη δική σου επιλογή:'.encode(),response.data)
        self.assertIn(review['reason'],html.unescape(response.get_data(as_text=True)))

    def test_all_geometry_quizzes_filters_and_result_solutions(self):
        # Same 23×4×3 real request matrix as the algebra batch, now with prose choices.
        with patch('tests.test_question_content.release',side_effect=geometry_release):
            question_tests.QuestionReleaseTests.test_all_new_quizzes_filters_scores_hints_and_solutions(self)

    def test_new_geometry_preserves_existing_bank_and_attempts(self):
        algebra=json.loads((ROOT/'content/questions/gym-a-algebra.v1.json').read_text(encoding='utf-8'))
        apply_release(self.db,algebra)
        old=[tuple(r) for r in self.db.execute('SELECT * FROM question_versions ORDER BY id')]
        oldunit=validate_release(algebra)[0][0]['id']
        attempt=self.repo.start_attempt(oldunit,'hard')
        geometry=geometry_release()
        self.assertEqual(apply_release(self.db,geometry),138)
        self.assertEqual(apply_release(self.db,geometry),0)
        self.assertEqual(self.repo.attempt(attempt['id']),attempt)
        for row in old:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM question_versions WHERE id=?',(row[0],)).fetchone()),row)
        report=coverage(self.db)
        self.assertEqual(report['active_questions'],762)
        self.assertEqual(report['first_pass_complete_units'],47)
        self.assertEqual(report['units_with_quiz'],63)
        self.assertEqual(report['remaining_units'],278)
        deploy_releases(self.db)

    def test_failed_geometry_baseline_rolls_back_whole_release(self):
        base=geometry_release();apply_release(self.db,base)
        revisions=copy.deepcopy(base);revisions['entries']=revisions['entries'][:2]
        for e in revisions['entries']:
            _,_,qid,_=validate_release({**base,'entries':[e]})[0]
            e['expected_current']=self.db.execute('SELECT version_id FROM current_questions WHERE question_id=?',(qid,)).fetchone()[0]
            e['payload']['hint']+=' Έλεγξε την κατασκευή.'
        revisions['entries'][1]['expected_current']='stale'
        pointers=[tuple(r) for r in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')]
        with self.assertRaises(ValueError):apply_release(self.db,revisions)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM current_questions ORDER BY question_id')],pointers)
