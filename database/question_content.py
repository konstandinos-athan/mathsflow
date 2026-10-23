"""Validated question releases. Existing attempts keep immutable version IDs."""
import argparse
import json
import re
import unicodedata
from fractions import Fraction
from pathlib import Path
from . import ROOT, DEFAULT_PATH, connect, copy_database, digest
from .importer import stable, validate_question, add_question_version
from .theory_content import arithmetic


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def number(text):
    value = text.strip().replace('−', '-').replace(',', '.')
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?(?:/[+-]?\d+)?', value):
        raise ValueError('Numeric choices must be explicit rational numbers')
    return Fraction(value)


def validate_release(release):
    if release.get('schema_version') != 1 or release.get('educator_review') != 'pending':
        raise ValueError('Invalid question release or review status')
    catalog = json.loads((ROOT / 'curriculum/catalog-2026-2027.json').read_text(encoding='utf-8'))
    course = next((c for c in catalog['courses'] if c['key'] == release.get('course')), None)
    if course is None or not isinstance(release.get('entries'), list) or not release['entries']:
        raise ValueError('Missing course/questions')
    units = {u['reference']: u for u in catalog['units'] if u['course_id'] == course['id']}
    prepared, ids, prompts = [], set(), set()
    for entry in release['entries']:
        unit = units.get(entry.get('reference'))
        slug = entry.get('key', '')
        if unit is None or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
            raise ValueError('Invalid unit or stable question key')
        qid = stable('bank-question/' + unit['id'] + '/' + slug)
        if qid in ids or 'expected_current' not in entry:
            raise ValueError('Duplicate ID or missing baseline')
        ids.add(qid)
        payload = entry['payload']
        validate_question(payload)
        if len(payload['choices']) != 4:
            raise ValueError('Question needs four choices')
        prompt = normalized(payload['question'])
        if prompt in prompts:
            raise ValueError('Duplicate question prompt')
        prompts.add(prompt)
        if len({normalized(c) for c in payload['choices']}) != 4:
            raise ValueError('Equivalent/duplicate choices')
        texts = [payload['question'], *payload['choices']]
        for key in ('hint', 'solution', 'skill'):
            value = payload.get(key)
            if not isinstance(value, str) or len(value.strip()) < 10:
                raise ValueError('Missing ' + key)
            texts.append(value)
        for text in texts:
            if '\ufffd' in text or re.search(r'<[^>]*>', text) or re.search(r'\\\\[()\[\]]', text):
                raise ValueError('Invalid text or doubled mathematics delimiter')
            if text.count('\\(') != text.count('\\)') or text.count('\\[') != text.count('\\]'):
                raise ValueError('Unbalanced mathematics delimiters')
        objective_ids = payload.get('objective_ids')
        allowed = {o['id'] for o in unit['learning_objectives']}
        if not isinstance(objective_ids, list) or not objective_ids or len(set(objective_ids)) != len(objective_ids) or set(objective_ids) - allowed:
            raise ValueError('Question objectives do not belong to its unit')
        if payload.get('source_refs') != unit['source_refs'] or payload.get('teaching_scope') != unit['teaching_scope'] or payload.get('educator_review') != 'pending':
            raise ValueError('Missing curriculum provenance')
        verification = payload.get('verification', {})
        if verification.get('kind') != 'numeric':
            raise ValueError('Unsupported verification kind')
        values = [number(c) for c in payload['choices']]
        if len(set(values)) != 4:
            raise ValueError('Numerically equivalent choices')
        result = arithmetic(verification['expression'])
        if values.count(result) != 1 or number(payload['answer']) != result:
            raise ValueError('Answer does not match exact calculation')
        prepared.append((unit, entry, qid, payload))
    return prepared


def apply_release(connection, release):
    prepared = validate_release(release)
    connection.execute('BEGIN IMMEDIATE')
    try:
        changed = 0
        for unit, entry, qid, payload in prepared:
            desired = stable('question-version/' + qid + '/' + digest(payload))
            existing = connection.execute('SELECT unit_id FROM questions WHERE id=?', (qid,)).fetchone()
            current = connection.execute('SELECT version_id FROM current_questions WHERE question_id=?', (qid,)).fetchone()
            current = current[0] if current else None
            if existing and existing[0] != unit['id']:
                raise ValueError('Question moved to another unit')
            if current == desired:
                continue
            if current != entry['expected_current']:
                raise ValueError('Question changed since release baseline')
            # Reject duplicate active prompts even across separate releases.
            for row in connection.execute('SELECT q.id,v.payload FROM questions q JOIN current_questions c ON c.question_id=q.id JOIN question_versions v ON v.id=c.version_id WHERE q.unit_id=?', (unit['id'],)):
                if row['id'] != qid and normalized(json.loads(row['payload'])['question']) == normalized(payload['question']):
                    raise ValueError('Duplicate active question prompt')
            if existing is None:
                order = connection.execute('SELECT COALESCE(MAX(display_order),0)+1 FROM questions WHERE unit_id=?', (unit['id'],)).fetchone()[0]
                connection.execute('INSERT INTO questions VALUES (?,?,?)', (qid, unit['id'], order))
            add_question_version(connection, qid, payload)
            changed += 1
        connection.commit()
        return changed
    except Exception:
        connection.rollback()
        raise


def deploy_releases(connection):
    latest = {}
    for path in sorted((ROOT / 'content/questions').glob('*.v*.json'), key=lambda p: (p.name.split('.v')[0], int(re.search(r'\.v(\d+)\.json$', p.name)[1]))):
        release = json.loads(path.read_text(encoding='utf-8'))
        pending = []
        for unit, entry, qid, payload in validate_release(release):
            desired = stable('question-version/' + qid + '/' + digest(payload))
            latest[qid] = desired
            history = connection.execute('SELECT question_id,content_hash FROM question_versions WHERE id=?', (desired,)).fetchone()
            if history:
                if history['question_id'] != qid or history['content_hash'] != digest(payload):
                    raise ValueError('Question history mismatch')
            else:
                pending.append(entry)
        if pending:
            apply_release(connection, {**release, 'entries': pending})
    for qid, desired in latest.items():
        current = connection.execute('SELECT version_id FROM current_questions WHERE question_id=?', (qid,)).fetchone()
        if current is None or current[0] != desired:
            raise ValueError('Active question differs from deployment releases; manual review required')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check','apply'])
    parser.add_argument('release', type=Path)
    parser.add_argument('--database', type=Path, default=DEFAULT_PATH)
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    release = json.loads(args.release.read_text(encoding='utf-8'))
    prepared = validate_release(release)
    if args.action == 'check':
        print(f'Validated {len(prepared)} questions; educator review pending.')
        return
    if not args.backup:
        parser.error('apply requires a new --backup file')
    copy_database(args.database,args.backup)
    db = connect(args.database)
    try:
        print(f'Applied {apply_release(db,release)} question revisions.')
    finally:
        db.close()


if __name__ == '__main__':
    main()
