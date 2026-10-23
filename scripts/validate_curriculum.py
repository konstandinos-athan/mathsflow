"""Offline structural validation of the annual curriculum and legacy crosswalk."""
import json
import hashlib
import re
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]


def validate():
    catalog = json.loads((ROOT / 'curriculum/catalog-2026-2027.json').read_text(encoding='utf-8'))
    sources = json.loads((ROOT / 'curriculum/sources.json').read_text(encoding='utf-8'))
    expected = json.loads((ROOT / 'curriculum/expected-references.json').read_text(encoding='utf-8'))
    source_ids = {s['id'] for s in sources}
    courses = {c['id']: c for c in catalog['courses']}
    chapters = {c['id']: c for c in catalog['chapters']}
    skills = {s['id']: s for s in catalog['prerequisite_skills']}
    all_ids = []
    for collection in ('courses', 'chapters', 'units'):
        for row in catalog[collection]:
            UUID(row['id'])
            all_ids.append(row['id'])
    assert len(all_ids) == len(set(all_ids)), 'Duplicate entity IDs'
    objective_ids = []
    legacy_routes = set()
    for unit in catalog['units']:
        assert unit['course_id'] in courses
        assert unit['chapter_id'] in chapters
        assert chapters[unit['chapter_id']]['course_id'] == unit['course_id']
        assert unit['title'] and not any(0xE000 <= ord(c) <= 0xF8FF for c in unit['title'])
        assert unit['source_refs']
        for reference in unit['source_refs']:
            assert reference['source_id'] in source_ids, reference
            assert reference.get('paragraph')
        assert unit['textbook_scope']['present'] is True
        assert unit['teaching_scope'] in ('required', 'modified', 'optional')
        assert unit['exam_scope'] in ('school', 'national_and_school', 'school_specific_not_preselected',
                                      'excluded_bridge', 'not_written_exam_under_current_list')
        assert len(unit['learning_objectives']) >= 2
        for objective in unit['learning_objectives']:
            UUID(objective['id'])
            objective_ids.append(objective['id'])
            assert objective['text'] and objective['origin']
        assert unit['prerequisites']
        assert all(p in skills for p in unit['prerequisites'])
        assert unit['coverage']['official_alignment'] == 'pending_content_review'
        if unit['legacy']:
            legacy = unit['legacy']
            route = tuple(legacy[k] for k in ('school', 'grade', 'subject', 'lesson_id'))
            assert route not in legacy_routes, 'Duplicate legacy route'
            legacy_routes.add(route)
    assert len(objective_ids) == len(set(objective_ids))
    for course in courses.values():
        units = [u for u in catalog['units'] if u['course_id'] == course['id']]
        assert [u['reference'] for u in units] == expected[course['key']], course['key']
        assert len({(u['book_id'], u['reference']) for u in units}) == len(units)
        assert all(s in source_ids for s in course['source_ids'])
        unit_ids = {u['id'] for u in catalog['units']}
        assert all(i in unit_ids for i in course.get('revision_unit_ids', []))
    visiting, visited = set(), set()

    def visit(key):
        assert key not in visiting, 'Prerequisite cycle: ' + key
        if key in visited:
            return
        visiting.add(key)
        for parent in skills[key]['prerequisites']:
            assert parent in skills
            visit(parent)
        visiting.remove(key)
        visited.add(key)

    for key in skills:
        visit(key)
    for source in sources:
        assert source['url'].startswith('https://')
        assert re.fullmatch('[0-9a-f]{64}', source['sha256'])
        assert source['checked_on'] == '2026-10-23'
        snapshot = ROOT / source['snapshot']
        assert snapshot.is_file(), snapshot
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == source['sha256'], snapshot
    return catalog


if __name__ == '__main__':
    result = validate()
    print(f"PASS: {len(result['courses'])} courses, {len(result['units'])} units; IDs, references, sources and prerequisite graph valid.")
