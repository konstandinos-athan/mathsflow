"""One-time validated import. Legacy Python modules are migration inputs only."""
import json
import time
import uuid
from pathlib import Path
from . import ROOT, digest, encode

NS = uuid.UUID('1a96ac2e-655f-45c3-8791-aa35bbde9719')


def stable(value):
    return str(uuid.uuid5(NS, value))


def validate_question(question):
    if not isinstance(question, dict) or not isinstance(question.get('question'), str) or not question['question'].strip():
        raise ValueError('Question must have a nonempty prompt')
    choices = question.get('choices')
    if not isinstance(choices, list) or len(choices) < 2 or any(not isinstance(c, str) or not c for c in choices):
        raise ValueError('Question must have at least two text choices')
    if len(set(choices)) != len(choices) or question.get('answer') not in choices:
        raise ValueError('Question choices/answer are invalid')
    if question.get('difficulty') not in ('easy', 'medium', 'hard'):
        raise ValueError('Invalid question difficulty')


def add_question_version(connection, question_id, payload):
    validate_question(payload)
    content_hash = digest(payload)
    version_id = stable('question-version/' + question_id + '/' + content_hash)
    connection.execute('INSERT OR IGNORE INTO question_versions VALUES (?,?,?,?,?,?)',
                       (version_id, question_id, content_hash, encode(payload), payload['difficulty'], time.time()))
    connection.execute('INSERT INTO current_questions VALUES (?,?) ON CONFLICT(question_id) DO UPDATE SET version_id=excluded.version_id', (question_id, version_id))
    return version_id


def add_theory_version(connection, unit_id, blocks):
    if not isinstance(blocks, list) or any(not isinstance(b, dict) or not isinstance(b.get('content'), str) for b in blocks):
        raise ValueError('Theory must contain text blocks')
    content_hash = digest(blocks)
    version_id = stable('theory-version/' + unit_id + '/' + content_hash)
    connection.execute('INSERT OR IGNORE INTO theory_versions VALUES (?,?,?,?,?)',
                       (version_id, unit_id, content_hash, encode(blocks), time.time()))
    connection.execute('INSERT INTO current_theory VALUES (?,?) ON CONFLICT(unit_id) DO UPDATE SET version_id=excluded.version_id', (unit_id, version_id))
    return version_id


def inputs():
    from scripts.validate_curriculum import validate
    from theory import theory_map
    from quiz_data import quiz_map
    catalog = validate()
    sources = json.loads((ROOT / 'curriculum/sources.json').read_text(encoding='utf-8'))
    legacy = {}
    for unit in catalog['units']:
        old = unit['legacy']
        if old:
            key = (old['grade'], old['subject'])
            legacy[unit['id']] = {'theory': theory_map.get(key, {}).get(old['title'], []),
                                  'questions': quiz_map.get(key, {}).get(old['title'], [])}
    return catalog, sources, legacy


def import_data(connection, catalog=None, sources=None, legacy=None):
    if catalog is None:
        catalog, sources, legacy = inputs()
    fingerprint = digest({'catalog': catalog, 'sources': sources, 'legacy': legacy})
    connection.execute('BEGIN IMMEDIATE')
    try:
        existing = connection.execute('SELECT content_hash, summary FROM import_runs WHERE name=?', ('initial-2026-2027',)).fetchone()
        if existing:
            if existing['content_hash'] != fingerprint:
                raise ValueError('Import inputs changed. Refusing to overwrite existing database; create an explicit content migration.')
            connection.rollback()
            return json.loads(existing['summary'])
        for school in catalog['schools']:
            connection.execute('INSERT INTO schools VALUES (?,?)', (school['id'], school['title']))
        for source in sources:
            connection.execute('INSERT INTO curriculum_sources VALUES (?,?)', (source['id'], encode(source)))
        for book in catalog['books']:
            connection.execute('INSERT INTO books VALUES (?,?,?)', (book['id'], book['source_id'], book['title']))
        grades = set()
        for course in catalog['courses']:
            if course['grade_id'] not in grades:
                connection.execute('INSERT INTO grades VALUES (?,?,?)', (course['grade_id'], course['school_id'], course['grade_title']))
                grades.add(course['grade_id'])
            subject = course['key'].split('-', 2)[2]
            subject_key = {'orientation': 'math-katefthinsis', 'general': 'math-general'}.get(subject, subject)
            connection.execute('INSERT INTO courses VALUES (?,?,?,?,?,?,?)', (course['id'], course['key'], course['grade_id'], subject_key, course['title'], course['school_year'], encode(course)))
        for chapter in catalog['chapters']:
            connection.execute('INSERT INTO chapters VALUES (?,?,?,?)', (chapter['id'], chapter['course_id'], chapter['book_id'], chapter['title']))
        for skill in catalog['prerequisite_skills']:
            connection.execute('INSERT INTO skills VALUES (?,?,?)', (skill['id'], skill['title'], encode(skill)))
        for skill in catalog['prerequisite_skills']:
            for parent in skill['prerequisites']:
                connection.execute('INSERT INTO skill_edges VALUES (?,?)', (skill['id'], parent))
        for unit in catalog['units']:
            connection.execute('INSERT INTO units VALUES (?,?,?,?,?,?,?)', (unit['id'], unit['course_id'], unit['chapter_id'], unit['reference'], unit['title'], unit['display_order'], encode(unit)))
            for objective in unit['learning_objectives']:
                connection.execute('INSERT INTO objectives VALUES (?,?,?)', (objective['id'], unit['id'], encode(objective)))
            for prerequisite in unit['prerequisites']:
                connection.execute('INSERT INTO unit_prerequisites VALUES (?,?)', (unit['id'], prerequisite))
            for i, source in enumerate(unit['source_refs']):
                connection.execute('INSERT INTO unit_sources VALUES (?,?,?,?)', (unit['id'], i, source['source_id'], encode(source)))
            old = unit['legacy']
            if old:
                connection.execute('INSERT INTO legacy_routes VALUES (?,?,?,?,?)', (old['school'], old['grade'], old['subject'], old['lesson_id'], unit['id']))
            content = legacy.get(unit['id'], {})
            if content.get('theory'):
                add_theory_version(connection, unit['id'], content['theory'])
            for i, question in enumerate(content.get('questions', []), 1):
                question_id = stable('legacy-question/' + unit['id'] + '/' + str(i))
                connection.execute('INSERT INTO questions VALUES (?,?,?)', (question_id, unit['id'], i))
                add_question_version(connection, question_id, question)
        summary = {table: connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                   for table in ('schools', 'grades', 'courses', 'chapters', 'units', 'objectives', 'legacy_routes', 'theory_versions', 'questions')}
        connection.execute('INSERT INTO import_runs VALUES (?,?,?,?)', ('initial-2026-2027', fingerprint, time.time(), encode(summary)))
        connection.commit()
        return summary
    except Exception:
        connection.rollback()
        raise
