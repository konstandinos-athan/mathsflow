import copy
import json

from database import ROOT
from database.importer import add_theory_version
from database.theory_content import apply_release, arithmetic, validate_release
from tests.support import DatabaseCase


class TheoryReleaseTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.release = json.loads((ROOT / 'content/theory/gym-a-algebra.v1.json').read_text(encoding='utf-8'))

    def test_complete_course_and_idempotent_import(self):
        prepared = validate_release(self.release)
        self.assertEqual(len(prepared), 24)
        self.assertEqual({u['reference'] for u, _, _ in prepared},
                         {r[0] for r in self.db.execute("SELECT reference FROM units WHERE course_id=(SELECT id FROM courses WHERE course_key='gym-a-algebra')")})
        self.assertEqual(apply_release(self.db, self.release), 24)
        self.assertEqual(apply_release(self.db, self.release), 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM theory_versions').fetchone()[0], 47)
        for unit, _, blocks in prepared:
            self.assertEqual(self.repo.theory(unit['id']), blocks)
            response = self.client.get('/study/unit/' + unit['id'])
            self.assertEqual(response.status_code, 200)
            self.assertIn('Λυμένο παράδειγμα', response.get_data(as_text=True))

    def test_conflict_rolls_back_whole_release(self):
        prepared = validate_release(self.release)
        last = prepared[-1][0]['id']
        add_theory_version(self.db, last, [{'content': 'An independent edit'}])
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'baseline'):
            apply_release(self.db, self.release)
        self.assertIsNone(self.db.execute('SELECT 1 FROM current_theory WHERE unit_id=?', (prepared[0][0]['id'],)).fetchone())
        self.assertEqual(self.repo.theory(last), [{'content': 'An independent edit'}])

    def test_bad_example_and_invalid_structure_rejected_before_write(self):
        for mutate in [lambda r: r['entries'][0]['checks'].append(['2+2', '=', '5']),
                       lambda r: r['entries'].append(copy.deepcopy(r['entries'][0])),
                       lambda r: r['entries'][0].update(explanation=''),
                       lambda r: r['entries'][0].update(example=r'Unbalanced mathematics expression \(x')]:
            bad = copy.deepcopy(self.release)
            mutate(bad)
            with self.assertRaises(ValueError):
                apply_release(self.db, bad)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM theory_versions').fetchone()[0], 23)

    def test_plain_text_content_cannot_inject_html(self):
        self.release['entries'][0]['example'] += '<script>alert(1)</script>'
        blocks = validate_release(self.release)[0][2]
        self.assertNotIn('<script>', blocks[3]['content'])
        self.assertIn('&lt;script&gt;', blocks[3]['content'])

    def test_checker_exact_and_no_executable_input(self):
        self.assertEqual(arithmetic('1/3+1/6'), arithmetic('1/2'))
        for expression in ['__import__("os")', '2**1000', '1.5', '[1][0]', '1/0']:
            with self.assertRaises((ValueError, ZeroDivisionError)):
                arithmetic(expression)

    def test_geometry_complete_and_all_47_pages_render(self):
        geometry = json.loads((ROOT / 'content/theory/gym-a-geometry.v1.json').read_text(encoding='utf-8'))
        prepared = validate_release(geometry)
        self.assertEqual(len(prepared), 23)
        self.assertEqual({u['reference'] for u, _, _ in prepared},
                         {r[0] for r in self.db.execute("SELECT reference FROM units WHERE course_id=(SELECT id FROM courses WHERE course_key='gym-a-geometry')")})
        self.assertEqual(apply_release(self.db, geometry), 23)
        self.assertEqual(apply_release(self.db, self.release), 24)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM current_theory').fetchone()[0], 70)
        for unit, _, _ in prepared:
            response = self.client.get('/study/unit/' + unit['id'])
            self.assertEqual(response.status_code, 200)
            self.assertIn('Ψηφιακό σχολικό βιβλίο', response.get_data(as_text=True))

    def test_second_grade_releases_cover_courses_and_preserve_initial_versions(self):
        before = [tuple(r) for r in self.db.execute('SELECT * FROM theory_versions ORDER BY id').fetchall()]
        for course, count in [('gym-b-algebra', 17), ('gym-b-geometry', 14)]:
            release = json.loads((ROOT / f'content/theory/{course}.v1.json').read_text(encoding='utf-8'))
            prepared = validate_release(release)
            expected = {r[0] for r in self.db.execute('SELECT id FROM units WHERE course_id=(SELECT id FROM courses WHERE course_key=?)', (course,)).fetchall()}
            self.assertEqual({u['id'] for u, _, _ in prepared}, expected)
            self.assertEqual(apply_release(self.db, release), count)
            self.assertEqual(apply_release(self.db, release), 0)
            for unit, _, blocks in prepared:
                self.assertEqual(self.repo.theory(unit['id']), blocks)
                page = self.client.get('/study/unit/' + unit['id'])
                self.assertEqual(page.status_code, 200)
                self.assertNotIn('Δεν υπάρχει ακόμα θεωρία', page.get_data(as_text=True))
                if unit['exam_scope'] == 'excluded_bridge':
                    self.assertIn('δεν αποτελεί εξεταστέα ύλη', page.get_data(as_text=True))
                if course == 'gym-b-algebra' and unit['reference'] == '4.1':
                    self.assertIn('δεν αποτελούν εξεταστέα ύλη', page.get_data(as_text=True))
                for block in blocks:
                    if '<img ' in block['content']:
                        import re
                        src = re.search(r'src="([^"]+)"', block['content'])[1]
                        with self.client.get(src) as image_response:
                            self.assertEqual(image_response.status_code, 200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM current_theory').fetchone()[0], 54)
        for row in before:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM theory_versions WHERE id=?', (row[0],)).fetchone()), row)

    def test_third_grade_complete_courses_scope_and_domain_examples(self):
        for course, count in [('gym-c-algebra', 19), ('gym-c-geometry', 7)]:
            release = json.loads((ROOT / f'content/theory/{course}.v1.json').read_text(encoding='utf-8'))
            prepared = validate_release(release)
            expected = {r[0] for r in self.db.execute('SELECT id FROM units WHERE course_id=(SELECT id FROM courses WHERE course_key=?)', (course,)).fetchall()}
            self.assertEqual({u['id'] for u, _, _ in prepared}, expected)
            self.assertEqual(apply_release(self.db, release), count)
            self.assertEqual(apply_release(self.db, release), 0)
            for unit, entry, blocks in prepared:
                with self.subTest(course=course, reference=unit['reference']):
                    page = self.client.get('/study/unit/' + unit['id'])
                    self.assertEqual(page.status_code, 200)
                    self.assertIn('Λυμένο παράδειγμα', page.get_data(as_text=True))
                    if 'scope_note' in entry:
                        self.assertIn(entry['scope_note'], page.get_data(as_text=True))
                    for block in blocks:
                        if '<img ' in block['content']:
                            import re
                            src = re.search(r'src="([^"]+)"', block['content'])[1]
                            with self.client.get(src) as image_response:
                                self.assertEqual(image_response.status_code, 200)
            if course == 'gym-c-algebra':
                entries = {e['reference']: e for e in release['entries']}
                self.assertIn('x≠3', entries['1.9']['example'])
                self.assertIn('x≠0 και x≠1', entries['1.10']['example'])
                self.assertIn('ισοπίθανα', entries['5.3']['explanation'])
                self.assertIn('προαιρετικά', entries['1.8']['scope_note'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM current_theory').fetchone()[0], 49)

    def test_lyceum_first_grade_revision_and_new_course_preserve_history(self):
        old_versions = [tuple(r) for r in self.db.execute('SELECT * FROM theory_versions').fetchall()]
        old_questions = [tuple(r) for r in self.db.execute('SELECT * FROM question_versions ORDER BY id').fetchall()]
        for course in ['gel-a-algebra', 'epal-a-algebra']:
            release = json.loads((ROOT / f'content/theory/{course}.v1.json').read_text(encoding='utf-8'))
            prepared = validate_release(release)
            expected = {r[0] for r in self.db.execute('SELECT id FROM units WHERE course_id=(SELECT id FROM courses WHERE course_key=?)', (course,)).fetchall()}
            self.assertEqual(len(prepared), 16)
            self.assertEqual({u['id'] for u, _, _ in prepared}, expected)
            self.assertEqual(apply_release(self.db, release), 16)
            self.assertEqual(apply_release(self.db, release), 0)
            for unit, entry, blocks in prepared:
                self.assertEqual(self.repo.theory(unit['id']), blocks)
                page = self.client.get('/study/unit/' + unit['id'])
                self.assertEqual(page.status_code, 200)
                self.assertIn('Λυμένο παράδειγμα', page.get_data(as_text=True))
                for block in blocks:
                    self.assertNotIn(r'\\(', block['content'])
                    self.assertNotIn(r'\nΓιατί', block['content'])
                    if '<img ' in block['content']:
                        import re
                        src = re.search(r'src="([^"]+)"', block['content'])[1]
                        with self.client.get(src) as image_response:
                            self.assertEqual(image_response.status_code, 200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM current_theory').fetchone()[0], 39)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM theory_versions').fetchone()[0], 55)
        for row in old_versions:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM theory_versions WHERE id=?', (row[0],)).fetchone()), row)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM question_versions ORDER BY id').fetchall()], old_questions)

    def test_lyceum_scope_separates_gel_and_epal(self):
        gel = json.loads((ROOT / 'content/theory/gel-a-algebra.v1.json').read_text(encoding='utf-8'))
        epal = json.loads((ROOT / 'content/theory/epal-a-algebra.v1.json').read_text(encoding='utf-8'))
        gel_entries = {e['reference']: e for e in gel['entries']}
        epal_entries = {e['reference']: e for e in epal['entries']}
        self.assertIn('Η απόσταση Α', gel_entries['6.2']['explanation'])
        self.assertNotIn('Η απόσταση Α', epal_entries['6.2']['explanation'])
        self.assertIn('Δεν διδάσκονται απόσταση σημείων', epal_entries['6.2']['scope_note'])
        self.assertIn('Για τη γενική απόδειξη', gel_entries['3.3']['explanation'])
        self.assertNotIn('Για τη γενική απόδειξη', epal_entries['3.3']['explanation'])
        self.assertIn('Δεν περιλαμβάνονται αποδείξεις ή παραμετρικές', epal_entries['3.3']['scope_note'])
        self.assertTrue(all(e['expected_current'] for e in gel['entries']))
        self.assertTrue(all(e['expected_current'] is None for e in epal['entries']))

    def test_first_grade_geometry_releases_complete_and_safe_to_reapply(self):
        before = [tuple(r) for r in self.db.execute('SELECT * FROM current_theory ORDER BY unit_id').fetchall()]
        for course, count in [('gel-a-geometry', 33), ('epal-a-geometry', 22)]:
            release = json.loads((ROOT / f'content/theory/{course}.v1.json').read_text(encoding='utf-8'))
            prepared = validate_release(release)
            expected = {r[0] for r in self.db.execute('SELECT id FROM units WHERE course_id=(SELECT id FROM courses WHERE course_key=?)',(course,)).fetchall()}
            self.assertEqual({u['id'] for u, _, _ in prepared}, expected)
            self.assertEqual(apply_release(self.db, release), count)
            self.assertEqual(apply_release(self.db, release), 0)
            for unit, entry, blocks in prepared:
                self.assertEqual(self.repo.theory(unit['id']), blocks)
                page = self.client.get('/study/unit/' + unit['id'])
                self.assertEqual(page.status_code, 200)
                self.assertIn('Λυμένο παράδειγμα', page.get_data(as_text=True))
                for block in blocks:
                    if '<img ' in block['content']:
                        import re
                        src = re.search(r'src="([^"]+)"', block['content'])[1]
                        with self.client.get(src) as image_response:
                            self.assertEqual(image_response.status_code, 200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM current_theory').fetchone()[0], 78)
        for row in before:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM current_theory WHERE unit_id=?',(row[0],)).fetchone()), row)

    def test_first_grade_geometry_proof_and_chapter_boundaries(self):
        gel = json.loads((ROOT / 'content/theory/gel-a-geometry.v1.json').read_text(encoding='utf-8'))
        epal = json.loads((ROOT / 'content/theory/epal-a-geometry.v1.json').read_text(encoding='utf-8'))
        g = {e['reference']:e for e in gel['entries']}
        e = {e['reference']:e for e in epal['entries']}
        self.assertIn('5.9', g)
        self.assertFalse(any(ref.startswith('5.') for ref in e))
        self.assertIn('Για τη συνδρομή μεσοκαθέτων', g['4.5']['explanation'])
        self.assertNotIn('Για τη συνδρομή μεσοκαθέτων', e['4.5']['explanation'])
        self.assertIn('χωρίς τις αποδείξεις', e['4.5']['scope_note'])
        self.assertNotIn('ορθοκεντρική τετράδα', g['5.8']['explanation'])
        self.assertIn('δ=R−r>0', g['3.16']['explanation'])
        self.assertIn('ταυτίζονται', g['3.16']['explanation'])

    def test_second_grade_orientation_complete_routes_and_reapplication(self):
        release = json.loads((ROOT / 'content/theory/gel-b-orientation.v1.json').read_text(encoding='utf-8'))
        prepared = validate_release(release)
        expected = {r[0] for r in self.db.execute("SELECT id FROM units WHERE course_id=(SELECT id FROM courses WHERE course_key='gel-b-orientation')").fetchall()}
        self.assertEqual(len(prepared), 13)
        self.assertEqual({u['id'] for u, _, _ in prepared}, expected)
        self.assertEqual(apply_release(self.db, release), 13)
        self.assertEqual(apply_release(self.db, release), 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM current_theory').fetchone()[0], 36)
        self.assertEqual(self.client.get('/school/gel/b-gel/math-katefthinsis').status_code, 200)
        for unit, _, blocks in prepared:
            self.assertEqual(self.repo.theory(unit['id']), blocks)
            with self.client.get('/study/unit/' + unit['id']) as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn('Λυμένο παράδειγμα', response.get_data(as_text=True))
            for block in blocks:
                if '<img ' in block['content']:
                    import re
                    src = re.search(r'src="([^"]+)"',block['content'])[1]
                    with self.client.get(src) as image_response:
                        self.assertEqual(image_response.status_code, 200)

    def test_orientation_preserves_restricted_scope_and_degenerate_cases(self):
        release = json.loads((ROOT / 'content/theory/gel-b-orientation.v1.json').read_text(encoding='utf-8'))
        entries = {e['reference']:e for e in release['entries']}
        self.assertIn('μόνο σχετική θέση ευθείας και κωνικής', entries['3.5']['explanation'])
        self.assertIn('γραμμική −4x=0, όχι διπλή ρίζα', entries['3.5']['example'])
        self.assertIn('δεν είναι εφαπτομένη', entries['3.5']['example'])
        self.assertIn('0<a<c', entries['3.4']['explanation'])
        self.assertIn('απόλυτη διαφορά', entries['3.4']['explanation'])
        self.assertIn('a>c>0', entries['3.3']['explanation'])
        self.assertIn('δεν του αποδίδουμε γωνία', entries['1.5']['explanation'])
        self.assertIn('Για D=0 ελέγχουμε', entries['2.2']['explanation'])

    def test_second_grade_algebra_complete_and_preserves_existing_theory(self):
        before = [tuple(r) for r in self.db.execute('SELECT * FROM current_theory ORDER BY unit_id')]
        for course, count in [('gel-b-algebra', 15), ('epal-b-algebra', 11)]:
            release = json.loads((ROOT / f'content/theory/{course}.v1.json').read_text(encoding='utf-8'))
            prepared = validate_release(release)
            expected = {r[0] for r in self.db.execute('SELECT id FROM units WHERE course_id=(SELECT id FROM courses WHERE course_key=?)', (course,))}
            self.assertEqual({u['id'] for u, _, _ in prepared}, expected)
            self.assertEqual(apply_release(self.db, release), count)
            self.assertEqual(apply_release(self.db, release), 0)
            for unit, _, blocks in prepared:
                self.assertEqual(self.repo.theory(unit['id']), blocks)
                with self.client.get('/study/unit/' + unit['id']) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('Λυμένο παράδειγμα', response.get_data(as_text=True))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM current_theory').fetchone()[0], 49)
        for row in before:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM current_theory WHERE unit_id=?', (row[0],)).fetchone()), row)

    def test_second_grade_algebra_distinct_epal_scope(self):
        entries = {}
        for course in ['gel-b-algebra', 'epal-b-algebra']:
            release = json.loads((ROOT / f'content/theory/{course}.v1.json').read_text(encoding='utf-8'))
            entries[course] = {e['reference']: e for e in release['entries']}
        gel, epal = entries['gel-b-algebra'], entries['epal-b-algebra']
        self.assertEqual(set(gel) - set(epal), {'3.2', '3.3', '3.5', '4.4'})
        for ref in ['5.1', '5.3']:
            self.assertIn('Δεν διδάσκονται', epal[ref]['scope_note'])
        self.assertIn('2^(x+1)=8', gel['5.1']['example'])
        self.assertNotIn('2^(x+1)=8', epal['5.1']['example'])
        self.assertIn('log(x−1)+log(x+1)', gel['5.3']['example'])
        self.assertNotIn('log(x−1)+log(x+1)', epal['5.3']['example'])
        for course in entries.values():
            self.assertIn('Δεν περιλαμβάνεται αλλαγή βάσης', course['5.2']['explanation'])

    def test_second_grade_geometry_complete_routes_and_preservation(self):
        before = [tuple(r) for r in self.db.execute('SELECT * FROM current_theory ORDER BY unit_id')]
        for course in ['gel-b-geometry', 'epal-b-geometry']:
            release = json.loads((ROOT / f'content/theory/{course}.v1.json').read_text(encoding='utf-8'))
            prepared = validate_release(release)
            expected = {r[0] for r in self.db.execute('SELECT id FROM units WHERE course_id=(SELECT id FROM courses WHERE course_key=?)', (course,))}
            self.assertEqual({u['id'] for u, _, _ in prepared}, expected)
            self.assertEqual(apply_release(self.db, release), 22)
            self.assertEqual(apply_release(self.db, release), 0)
            for unit, _, blocks in prepared:
                self.assertEqual(self.repo.theory(unit['id']), blocks)
                with self.client.get('/study/unit/' + unit['id']) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('Λυμένο παράδειγμα', response.get_data(as_text=True))
                if unit['reference']=='9.2':
                    self.assertTrue(any('right-triangle-projections.svg' in b['content'] for b in blocks))
                for block in blocks:
                    if '<img ' in block['content']:
                        import re
                        src = re.search(r'src="([^"]+)"', block['content'])[1]
                        with self.client.get(src) as image_response:
                            self.assertEqual(image_response.status_code, 200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM current_theory').fetchone()[0], 67)
        for row in before:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM current_theory WHERE unit_id=?', (row[0],)).fetchone()), row)

    def test_second_grade_geometry_course_boundaries_and_excluded_proofs(self):
        entries={}
        for course in ['gel-b-geometry', 'epal-b-geometry']:
            release=json.loads((ROOT / f'content/theory/{course}.v1.json').read_text(encoding='utf-8'))
            entries[course]={e['reference']:e for e in release['entries']}
        gel,epal=entries['gel-b-geometry'],entries['epal-b-geometry']
        self.assertTrue(all(str(i) + '.' in ' '.join(gel) for i in [7,8,9,10,11]))
        self.assertFalse(any(r.startswith('5.') for r in gel))
        self.assertFalse(any(r.startswith(('10.','11.')) for r in epal))
        self.assertEqual(len([r for r in epal if r.startswith('5.')]),11)
        self.assertNotIn('ΑΜ=λc/(1+λ)',epal['7.6']['explanation'])
        self.assertIn('ΑΜ=λc/(1+λ)',gel['7.6']['explanation'])
        self.assertNotIn('κατάλληλα τρίγωνα είναι ίσα',epal['5.3']['explanation'])
        self.assertNotIn('αφού ίσα ορθογώνια τρίγωνα',epal['5.4']['explanation'])
        self.assertNotIn('Κατεβάζοντας κάθετες',epal['5.11']['explanation'])
        self.assertNotIn('a²=h²+(c−p)²',epal['9.4']['explanation'])
        self.assertIn('a²=h²+(c−p)²',gel['9.4']['explanation'])

    def test_third_grade_gel_complete_and_preserves_existing_theory(self):
        before = [tuple(r) for r in self.db.execute('SELECT * FROM current_theory ORDER BY unit_id')]
        for course,count in [('gel-c-general',11),('gel-c-orientation',22)]:
            release=json.loads((ROOT / f'content/theory/{course}.v1.json').read_text(encoding='utf-8'))
            prepared=validate_release(release)
            expected={r[0] for r in self.db.execute('SELECT id FROM units WHERE course_id=(SELECT id FROM courses WHERE course_key=?)',(course,))}
            self.assertEqual({u['id'] for u,_,_ in prepared},expected)
            self.assertEqual(apply_release(self.db,release),count)
            self.assertEqual(apply_release(self.db,release),0)
            for unit,_,blocks in prepared:
                self.assertEqual(self.repo.theory(unit['id']),blocks)
                with self.client.get('/study/unit/'+unit['id']) as response:
                    self.assertEqual(response.status_code,200)
                    self.assertIn('Λυμένο παράδειγμα',response.get_data(as_text=True))
                for block in blocks:
                    if '<img ' in block['content']:
                        import re
                        src=re.search(r'src="([^"]+)"',block['content'])[1]
                        with self.client.get(src) as image_response:
                            self.assertEqual(image_response.status_code,200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM current_theory').fetchone()[0],56)
        for row in before:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM current_theory WHERE unit_id=?',(row[0],)).fetchone()),row)

    def test_third_grade_gel_scope_and_statistical_interpretation(self):
        general=json.loads((ROOT / 'content/theory/gel-c-general.v1.json').read_text(encoding='utf-8'))
        orientation=json.loads((ROOT / 'content/theory/gel-c-orientation.v1.json').read_text(encoding='utf-8'))
        g={e['reference']:e for e in general['entries']}
        o={e['reference']:e for e in orientation['entries']}
        self.assertFalse({'3.2','3.3','3.6'} & set(o))
        self.assertIn('χωρίς διαδικασίες ολοκλήρωσης κατά μέρη ή αντικατάστασης',o['3.1']['example'])
        self.assertIn('δεν δίνονται ασκήσεις με μεταβλητό άνω όριο',o['3.5']['explanation'])
        self.assertIn('μόνο με σταθερά άκρα',o['3.5']['example'])
        self.assertIn('Δεν χρησιμοποιείται κριτήριο δεύτερης παραγώγου',o['2.7']['explanation'])
        self.assertIn('τουλάχιστον δύο φορές παραγωγίσιμες',o['2.8']['explanation'])
        self.assertIn('με ισοπίθανα απλά αποτελέσματα',g['1.2']['explanation'])
        self.assertIn('CV κοντά σε μηδενικό μέσο είναι ακατάλληλο',g['2.3']['mistake'])
        self.assertIn('Συσχέτιση δεν συνεπάγεται αιτιότητα',g['2.7']['explanation'])
        self.assertIn('r=0 δεν αποκλείει μη γραμμική σχέση',g['2.7']['explanation'])

    def test_epal_final_releases_revision_history_and_full_course_coverage(self):
        old_versions=[tuple(r) for r in self.db.execute('SELECT * FROM theory_versions ORDER BY id')]
        old_questions=[tuple(r) for r in self.db.execute('SELECT * FROM question_versions ORDER BY id')]
        before={r['unit_id']:tuple(r) for r in self.db.execute('SELECT * FROM current_theory')}
        revised=set()
        for course,count in [('epal-c-geometry',11),('epal-c-algebra',7)]:
            release=json.loads((ROOT / f'content/theory/{course}.v1.json').read_text(encoding='utf-8'))
            prepared=validate_release(release)
            expected={r[0] for r in self.db.execute('SELECT id FROM units WHERE course_id=(SELECT id FROM courses WHERE course_key=?)',(course,))}
            self.assertEqual({u['id'] for u,_,_ in prepared},expected)
            if course=='epal-c-algebra':
                revised={u['id'] for u,_,_ in prepared}
                for unit,entry,_ in prepared:
                    self.assertEqual(self.db.execute('SELECT version_id FROM current_theory WHERE unit_id=?',(unit['id'],)).fetchone()[0],entry['expected_current'])
            self.assertEqual(apply_release(self.db,release),count)
            self.assertEqual(apply_release(self.db,release),0)
            for unit,_,blocks in prepared:
                self.assertEqual(self.repo.theory(unit['id']),blocks)
                with self.client.get('/study/unit/'+unit['id']) as response:
                    self.assertEqual(response.status_code,200)
                    self.assertIn('Λυμένο παράδειγμα',response.get_data(as_text=True))
                for block in blocks:
                    if '<img ' in block['content']:
                        import re
                        src=re.search(r'src="([^"]+)"',block['content'])[1]
                        with self.client.get(src) as image_response:
                            self.assertEqual(image_response.status_code,200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM current_theory').fetchone()[0],34)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM theory_versions').fetchone()[0],41)
        for row in old_versions:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM theory_versions WHERE id=?',(row[0],)).fetchone()),row)
        for unit_id,row in before.items():
            current=tuple(self.db.execute('SELECT * FROM current_theory WHERE unit_id=?',(unit_id,)).fetchone())
            if unit_id in revised:self.assertNotEqual(current,row)
            else:self.assertEqual(current,row)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM question_versions ORDER BY id')],old_questions)

    def test_epal_final_releases_respect_narrower_syllabus(self):
        geo=json.loads((ROOT / 'content/theory/epal-c-geometry.v1.json').read_text(encoding='utf-8'))
        algebra=json.loads((ROOT / 'content/theory/epal-c-algebra.v1.json').read_text(encoding='utf-8'))
        g={e['reference']:e for e in geo['entries']}
        a={e['reference']:e for e in algebra['entries']}
        self.assertNotIn('11.3',g)
        self.assertNotIn('Κόβοντας και μεταφέροντας',g['10.3']['explanation'])
        self.assertNotIn('Από Ε=bh/2 προκύπτει',g['10.5']['explanation'])
        self.assertIn('μόνο αυτός ο πρόσθετος τύπος',g['10.4']['explanation'])
        self.assertNotIn('ημίτονο',g['10.4']['example'])
        self.assertNotIn('CV',g['10.4']['example'])
        self.assertIn('Το κριτήριο δεύτερης παραγώγου δεν περιλαμβάνεται',a['1.4']['explanation'])
        self.assertIn('Οι κλάσεις άνισου πλάτους εξαιρούνται',a['2.2']['explanation'])
        self.assertNotIn('Επικρατούσα',a['2.3']['explanation'])
        self.assertNotIn('IQR',a['2.3']['explanation'])
        self.assertIn('παρέχονται σύμφωνα με τις οδηγίες',a['2.3']['explanation'])
        self.assertTrue(all(e['expected_current'] is not None for e in algebra['entries']))
        self.assertTrue(all(e['expected_current'] is None for e in geo['entries']))

    def test_analysis_review_preserves_history_and_rejects_old_release_replay(self):
        v1=json.loads((ROOT / 'content/theory/gel-c-orientation.v1.json').read_text(encoding='utf-8'))
        v2=json.loads((ROOT / 'content/theory/gel-c-orientation.v2.json').read_text(encoding='utf-8'))
        self.assertEqual(apply_release(self.db,v1),22)
        previous=[tuple(r) for r in self.db.execute('SELECT * FROM theory_versions ORDER BY id')]
        pointers={r['unit_id']:tuple(r) for r in self.db.execute('SELECT * FROM current_theory')}
        prepared=validate_release(v2)
        targets={u['id'] for u,_,_ in prepared}
        self.assertEqual({e['reference'] for _,e,_ in prepared},{'1.8','2.6','2.7'})
        for unit,entry,_ in prepared:
            self.assertEqual(self.db.execute('SELECT version_id FROM current_theory WHERE unit_id=?',(unit['id'],)).fetchone()[0],entry['expected_current'])
        self.assertEqual(apply_release(self.db,v2),3)
        self.assertEqual(apply_release(self.db,v2),0)
        current=[tuple(r) for r in self.db.execute('SELECT * FROM current_theory ORDER BY unit_id')]
        with self.assertRaisesRegex(ValueError,'baseline'):
            apply_release(self.db,v1)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM current_theory ORDER BY unit_id')],current)
        for row in previous:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM theory_versions WHERE id=?',(row[0],)).fetchone()),row)
        for unit_id,row in pointers.items():
            if unit_id not in targets:
                self.assertEqual(tuple(self.db.execute('SELECT * FROM current_theory WHERE unit_id=?',(unit_id,)).fetchone()),row)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM theory_versions').fetchone()[0],48)
        for unit,_,blocks in prepared:
            self.assertEqual(self.repo.theory(unit['id']),blocks)
            with self.client.get('/study/unit/'+unit['id']) as response:
                self.assertEqual(response.status_code,200)
                self.assertIn('Λυμένο παράδειγμα',response.get_data(as_text=True))

    def test_analysis_review_explicit_hypotheses_and_counterexamples(self):
        release=json.loads((ROOT / 'content/theory/gel-c-orientation.v2.json').read_text(encoding='utf-8'))
        entries={e['reference']:e for e in release['entries']}
        self.assertIn('και συνεχής στο x₀',entries['2.7']['explanation'])
        self.assertIn('g(0)=1',entries['2.7']['example'])
        self.assertIn('δεν είναι συνεχής στο 0',entries['2.7']['example'])
        self.assertIn('είναι και οι δύο συνεχείς στο ίδιο διάστημα',entries['2.6']['explanation'])
        self.assertIn('δεν είναι συνεχής στο αριστερό άκρο',entries['2.6']['explanation'])
        self.assertIn('g(x)=f(x)−η',entries['1.8']['explanation'])
        self.assertIn('χωρίς να απαιτείται μονοτονία',entries['1.8']['explanation'])
        self.assertIn('Δεν χρησιμοποιείται κριτήριο δεύτερης παραγώγου',entries['2.7']['explanation'])

    def test_analysis_derivatives_revision_chain_keeps_first_review(self):
        releases=[json.loads((ROOT / f'content/theory/gel-c-orientation.v{i}.json').read_text(encoding='utf-8')) for i in [1,2,3]]
        self.assertEqual(apply_release(self.db,releases[0]),22)
        self.assertEqual(apply_release(self.db,releases[1]),3)
        before=[tuple(r) for r in self.db.execute('SELECT * FROM theory_versions ORDER BY id')]
        pointers={r['unit_id']:tuple(r) for r in self.db.execute('SELECT * FROM current_theory')}
        prepared=validate_release(releases[2])
        self.assertEqual({e['reference'] for _,e,_ in prepared},{'2.2','2.3','2.5'})
        targets={u['id'] for u,_,_ in prepared}
        self.assertEqual(apply_release(self.db,releases[2]),3)
        self.assertEqual(apply_release(self.db,releases[2]),0)
        for row in before:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM theory_versions WHERE id=?',(row[0],)).fetchone()),row)
        for unit_id,row in pointers.items():
            if unit_id not in targets:
                self.assertEqual(tuple(self.db.execute('SELECT * FROM current_theory WHERE unit_id=?',(unit_id,)).fetchone()),row)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM theory_versions').fetchone()[0],51)
        for unit,_,blocks in prepared:
            self.assertEqual(self.repo.theory(unit['id']),blocks)
            with self.client.get('/study/unit/'+unit['id']) as response:
                self.assertEqual(response.status_code,200)
                self.assertIn('Λυμένο παράδειγμα',response.get_data(as_text=True))

    def test_analysis_derivatives_hypotheses_and_excluded_proofs(self):
        release=json.loads((ROOT / 'content/theory/gel-c-orientation.v3.json').read_text(encoding='utf-8'))
        e={e['reference']:e for e in release['entries']}
        self.assertIn('στα άκρα μόνο συνέχεια',e['2.2']['explanation'])
        self.assertIn('Η απόδειξη του γινομένου εξαιρείται',e['2.3']['explanation'])
        self.assertIn('Η απόδειξη πηλίκου παραλείπεται',e['2.3']['explanation'])
        self.assertIn('της εσωτερικής',e['2.3']['explanation'])
        self.assertIn('όχι κοινό κλάσμα',e['2.3']['explanation'])
        self.assertIn('χωρίς τις εξαιρούμενες αποδείξεις',e['2.2']['explanation'])
        self.assertIn('χωρίς να απαιτούμε ίσες τιμές άκρων',e['2.5']['explanation'])
        self.assertIn('δύο λύσεις',e['2.5']['example'])
        self.assertIn('δεν αποδεικνύει αυτομάτως',e['2.5']['explanation'])

    def test_analysis_integrals_revision_preserves_previous_reviews(self):
        releases=[json.loads((ROOT / f'content/theory/gel-c-orientation.v{i}.json').read_text(encoding='utf-8')) for i in [1,2,3,4]]
        for release,count in zip(releases[:3],[22,3,3]):
            self.assertEqual(apply_release(self.db,release),count)
        old=[tuple(r) for r in self.db.execute('SELECT * FROM theory_versions ORDER BY id')]
        pointers={r['unit_id']:tuple(r) for r in self.db.execute('SELECT * FROM current_theory')}
        prepared=validate_release(releases[3])
        self.assertEqual({e['reference'] for _,e,_ in prepared},{'2.8','2.9','3.1','3.4','3.5','3.7'})
        targets={u['id'] for u,_,_ in prepared}
        self.assertEqual(apply_release(self.db,releases[3]),6)
        self.assertEqual(apply_release(self.db,releases[3]),0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM theory_versions').fetchone()[0],57)
        for row in old:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM theory_versions WHERE id=?',(row[0],)).fetchone()),row)
        for unit_id,row in pointers.items():
            if unit_id not in targets:
                self.assertEqual(tuple(self.db.execute('SELECT * FROM current_theory WHERE unit_id=?',(unit_id,)).fetchone()),row)
        for unit,_,blocks in prepared:
            self.assertEqual(self.repo.theory(unit['id']),blocks)
            with self.client.get('/study/unit/'+unit['id']) as response:
                self.assertEqual(response.status_code,200)
                self.assertIn('Λυμένο παράδειγμα',response.get_data(as_text=True))

    def test_analysis_integrals_scope_and_invalid_shortcuts(self):
        release=json.loads((ROOT / 'content/theory/gel-c-orientation.v4.json').read_text(encoding='utf-8'))
        e={e['reference']:e for e in release['entries']}
        self.assertIn('τουλάχιστον δύο φορές παραγωγίσιμες',e['2.8']['explanation'])
        self.assertIn('Πεπερασμένο όριο σε πεπερασμένο άκρο δεν ορίζει οριζόντια ασύμπτωτη',e['2.9']['explanation'])
        self.assertIn('δεν αποδεικνύει ότι δεν υπάρχει όριο',e['2.9']['explanation'])
        self.assertIn('χωρίς μεθόδους κατά μέρη ή αντικατάστασης',e['3.1']['explanation'])
        self.assertIn('Δεν διδάσκονται ασκήσεις ή εφαρμογές με μεταβλητό άνω όριο',e['3.5']['explanation'])
        self.assertIn('Μόνο σταθερά άκρα',e['3.5']['example'])
        self.assertIn('δεν επιτρέπεται η ίδια εφαρμογή',e['3.5']['example'])
        self.assertIn('Η εξαιρούμενη εφαρμογή 3',e['3.7']['explanation'])
        self.assertIn('αρνητικό ή μηδέν',e['3.4']['explanation'])

    def test_analysis_first_review_covers_all_units_without_erasing_history(self):
        releases=[json.loads((ROOT / f'content/theory/gel-c-orientation.v{i}.json').read_text(encoding='utf-8')) for i in range(1,6)]
        reviewed=[e['reference'] for release in releases[1:] for e in release['entries']]
        self.assertEqual(len(reviewed),22)
        self.assertEqual(set(reviewed),{e['reference'] for e in releases[0]['entries']})
        for release,count in zip(releases[:4],[22,3,3,6]):self.assertEqual(apply_release(self.db,release),count)
        old=[tuple(r) for r in self.db.execute('SELECT * FROM theory_versions ORDER BY id')]
        pointers={r['unit_id']:tuple(r) for r in self.db.execute('SELECT * FROM current_theory')}
        prepared=validate_release(releases[4]);targets={u['id'] for u,_,_ in prepared}
        self.assertEqual(apply_release(self.db,releases[4]),10)
        self.assertEqual(apply_release(self.db,releases[4]),0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM theory_versions').fetchone()[0],67)
        for row in old:self.assertEqual(tuple(self.db.execute('SELECT * FROM theory_versions WHERE id=?',(row[0],)).fetchone()),row)
        for unit_id,row in pointers.items():
            if unit_id not in targets:self.assertEqual(tuple(self.db.execute('SELECT * FROM current_theory WHERE unit_id=?',(unit_id,)).fetchone()),row)
        for unit,_,blocks in prepared:
            self.assertEqual(self.repo.theory(unit['id']),blocks)
            with self.client.get('/study/unit/'+unit['id']) as response:
                self.assertEqual(response.status_code,200)
                self.assertIn('Λυμένο παράδειγμα',response.get_data(as_text=True))

    def test_analysis_foundations_domains_and_rate_interpretation(self):
        r=json.loads((ROOT / 'content/theory/gel-c-orientation.v5.json').read_text(encoding='utf-8'))
        e={e['reference']:e for e in r['entries']}
        self.assertIn('κανείς από τους δύο δεν είναι η μηδενική συνάρτηση',e['1.2']['example'])
        self.assertIn('Η συμμετρία πεδίου δεν παραλείπεται',e['1.2']['explanation'])
        self.assertIn('Η f⁻¹ δεν είναι το κλάσμα 1/f',e['1.3']['explanation'])
        self.assertIn('δεν αποδεικνύει όριο',e['1.4']['explanation'])
        self.assertIn('Η αυστηρή ανισότητα μπορεί να χαθεί',e['1.5']['explanation'])
        self.assertIn('Η x/x στο 0 έχει όριο 1',e['1.6']['explanation'])
        self.assertIn('δεν αποτελεί γενική ακριβή ταυτότητα',e['2.1']['explanation'])
        self.assertIn('μέσο μέτρο ταχύτητας 5/3',e['2.4']['example'])
        self.assertIn('χωρίς καμπή στο μη ορισμένο 0',e['2.10']['example'])

    def test_statistics_review_keeps_history_and_course_boundaries(self):
        for course,count in [('gel-c-general',11),('epal-c-algebra',7)]:
            v1=json.loads((ROOT / f'content/theory/{course}.v1.json').read_text(encoding='utf-8'))
            self.assertEqual(apply_release(self.db,v1),count)
        previous=[tuple(r) for r in self.db.execute('SELECT * FROM theory_versions ORDER BY id')]
        pointers={r['unit_id']:tuple(r) for r in self.db.execute('SELECT * FROM current_theory')}
        targets=set()
        for course,count in [('gel-c-general',11),('epal-c-algebra',3)]:
            v2=json.loads((ROOT / f'content/theory/{course}.v2.json').read_text(encoding='utf-8'))
            prepared=validate_release(v2);targets.update(u['id'] for u,_,_ in prepared)
            self.assertEqual(apply_release(self.db,v2),count)
            self.assertEqual(apply_release(self.db,v2),0)
            for unit,_,blocks in prepared:
                self.assertEqual(self.repo.theory(unit['id']),blocks)
                with self.client.get('/study/unit/'+unit['id']) as response:
                    self.assertEqual(response.status_code,200)
                    self.assertIn('Λυμένο παράδειγμα',response.get_data(as_text=True))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM theory_versions').fetchone()[0],55)
        for row in previous:self.assertEqual(tuple(self.db.execute('SELECT * FROM theory_versions WHERE id=?',(row[0],)).fetchone()),row)
        for unit_id,row in pointers.items():
            if unit_id not in targets:self.assertEqual(tuple(self.db.execute('SELECT * FROM current_theory WHERE unit_id=?',(unit_id,)).fetchone()),row)

    def test_statistics_review_preserves_restricted_epal_and_interpretation(self):
        g=json.loads((ROOT / 'content/theory/gel-c-general.v2.json').read_text(encoding='utf-8'))
        e=json.loads((ROOT / 'content/theory/epal-c-algebra.v2.json').read_text(encoding='utf-8'))
        ge={x['reference']:x for x in g['entries']};ep={x['reference']:x for x in e['entries']}
        self.assertEqual(set(ep),{'2.1','2.2','2.3'})
        self.assertIn('Αξιωματική προσέγγιση',ge['1.2']['explanation'])
        self.assertIn('με την ίδια σύμβαση σειράς',ge['1.4']['explanation'])
        self.assertIn('νᵢ/πλάτος',ge['2.2']['explanation'])
        self.assertNotIn('νᵢ/πλάτος',ep['2.2']['explanation'])
        self.assertIn('IQR',ge['2.3']['explanation'])
        self.assertNotIn('IQR',ep['2.3']['explanation'])
        self.assertNotIn('Επικρατούσα',ep['2.3']['explanation'])
        self.assertIn('δεν διαγράφεται αυτόματα',ge['2.3']['explanation'])
        self.assertIn('Δεν απαιτείται απομνημόνευση του τύπου Pearson',ge['2.7']['explanation'])
        self.assertIn('πραγματικός μέσος',ge['2.2']['explanation'])
        self.assertTrue(all(x['expected_current'] for x in g['entries']+e['entries']))

    def test_epal_final_review_preserves_statistics_and_prior_versions(self):
        for filename,count in [('epal-c-algebra.v1',7),('epal-c-algebra.v2',3),('epal-c-geometry.v1',11)]:
            release=json.loads((ROOT / f'content/theory/{filename}.json').read_text(encoding='utf-8'))
            self.assertEqual(apply_release(self.db,release),count)
        previous=[tuple(r) for r in self.db.execute('SELECT * FROM theory_versions ORDER BY id')]
        pointers={r['unit_id']:tuple(r) for r in self.db.execute('SELECT * FROM current_theory')}
        targets=set()
        for filename,count in [('epal-c-algebra.v3',4),('epal-c-geometry.v2',11)]:
            release=json.loads((ROOT / f'content/theory/{filename}.json').read_text(encoding='utf-8'))
            prepared=validate_release(release);targets.update(u['id'] for u,_,_ in prepared)
            self.assertEqual(apply_release(self.db,release),count)
            self.assertEqual(apply_release(self.db,release),0)
            for unit,_,blocks in prepared:
                self.assertEqual(self.repo.theory(unit['id']),blocks)
                with self.client.get('/study/unit/'+unit['id']) as response:
                    self.assertEqual(response.status_code,200)
        self.assertEqual(len(targets),15)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM theory_versions').fetchone()[0],len(previous)+15)
        for row in previous:
            self.assertEqual(tuple(self.db.execute('SELECT * FROM theory_versions WHERE id=?',(row[0],)).fetchone()),row)
        for unit_id,row in pointers.items():
            if unit_id not in targets:
                self.assertEqual(tuple(self.db.execute('SELECT * FROM current_theory WHERE unit_id=?',(unit_id,)).fetchone()),row)

    def test_epal_final_review_matches_restricted_scope(self):
        algebra=json.loads((ROOT / 'content/theory/epal-c-algebra.v3.json').read_text(encoding='utf-8'))
        geometry=json.loads((ROOT / 'content/theory/epal-c-geometry.v2.json').read_text(encoding='utf-8'))
        a={e['reference']:e for e in algebra['entries']};g={e['reference']:e for e in geometry['entries']}
        self.assertEqual(set(a),{'1.1','1.2','1.3','1.4'})
        self.assertEqual(set(g),{'10.1','10.2','10.3','10.4','10.5','11.1','11.2','11.4','11.5','11.6','11.7'})
        self.assertIn('M≠0',a['1.1']['explanation'])
        self.assertIn('συνέχεια στο c',a['1.4']['explanation'])
        self.assertIn('Δεν απαιτείται να υπάρχει η παράγωγος',a['1.4']['explanation'])
        self.assertIn('χωρίς κριτήριο δεύτερης παραγώγου',a['1.3']['explanation'])
        self.assertIn('Δεν εισάγονται τύποι με ημίτονο',g['10.4']['explanation'])
        self.assertIn('όχι γνήσιο τρίγωνο',g['10.4']['explanation'])
        self.assertIn('χρειάζεται να γνωρίζουμε ότι τα σχήματα είναι όμοια',g['10.5']['explanation'])
        self.assertIn('12π+8',g['11.7']['example'])
        self.assertTrue(all(e['expected_current'] for e in algebra['entries']+geometry['entries']))
