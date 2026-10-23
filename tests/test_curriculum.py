import json
import unittest
from pathlib import Path
from scripts.validate_curriculum import validate

ROOT = Path(__file__).resolve().parents[1]


class CurriculumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = validate()

    def units(self, key):
        course = next(c for c in self.catalog['courses'] if c['key'] == key)
        return [u for u in self.catalog['units'] if u['course_id'] == course['id']]

    def test_all_nine_grades_and_required_course_splits(self):
        courses = self.catalog['courses']
        self.assertEqual(len(courses), 19)
        self.assertEqual(len({(c['school_id'], c['grade_id']) for c in courses}), 9)
        counts = [24, 23, 17, 14, 19, 7, 16, 33, 15, 22, 13, 11, 22, 16, 22, 11, 22, 7, 11]
        self.assertEqual([len(self.units(c['key'])) for c in courses], counts)

    def test_analysis_omits_non_syllabus_integration_sections(self):
        units = self.units('gel-c-orientation')
        references = {u['reference'] for u in units}
        self.assertEqual({r for r in references if r.startswith('3.')}, {'3.1', '3.4', '3.5', '3.7'})
        primitive = next(u for u in units if u['reference'] == '3.1')
        self.assertIn('παράγουσα', primitive['title'])
        self.assertTrue(primitive['restrictions'])

    def test_bridge_from_first_grade_is_not_exam_content_in_second(self):
        units = [u for u in self.units('gym-b-algebra') if u['book_id'] == 'gym-a']
        self.assertEqual([u['reference'] for u in units], ['7.7', '7.8', '7.9'])
        self.assertTrue(all(u['exam_scope'] == 'excluded_bridge' for u in units))

    def test_vocational_geometry_is_not_copied_from_same_grade_gel(self):
        a = {u['reference'] for u in self.units('epal-a-geometry')}
        b = {u['reference'] for u in self.units('epal-b-geometry')}
        c = {u['reference'] for u in self.units('epal-c-geometry')}
        self.assertNotIn('5.2', a)
        self.assertIn('5.2', b)
        self.assertIn('10.4', c)
        self.assertEqual(len(c), 11)

    def test_legacy_crosswalk_preserves_existing_content(self):
        units = self.catalog['units']
        self.assertEqual(sum(u['legacy'] is not None for u in units), 23)
        self.assertEqual(sum(u['coverage']['question_count'] for u in units), 480)
        self.assertEqual(sum(u['coverage']['theory'] == 'existing_unreviewed' for u in units), 23)
        self.assertTrue(all(u['coverage']['quiz'] == 'missing' for u in self.units('epal-c-algebra')))

    def test_sources_and_mapping_not_claimed_as_content_review(self):
        self.assertTrue(all(u['coverage']['official_alignment'] == 'pending_content_review' for u in self.catalog['units']))
        self.assertTrue(all(u['learning_objectives'][0]['origin'].startswith('MathsFlow') for u in self.catalog['units']))


if __name__ == '__main__':
    unittest.main()
