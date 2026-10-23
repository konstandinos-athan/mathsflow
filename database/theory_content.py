"""Explicit, atomic theory releases; initial migration inputs stay frozen."""
import argparse
import ast
import json
from fractions import Fraction
from html import escape
from pathlib import Path

from . import DEFAULT_PATH, ROOT, connect, copy_database, digest
from .importer import add_theory_version, stable


def arithmetic(expression):
    """Exact rational checks, without eval, names, calls or floating point."""
    if not isinstance(expression, str) or len(expression) > 300:
        raise ValueError('Invalid arithmetic expression')
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) is int and abs(node.value) < 10**12:
            return Fraction(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): return a + b
            if isinstance(node.op, ast.Sub): return a - b
            if isinstance(node.op, ast.Mult): return a * b
            if isinstance(node.op, ast.Div): return a / b
            if isinstance(node.op, ast.Pow) and b.denominator == 1 and 0 <= b <= 12:
                return a ** int(b)
        raise ValueError('Unsupported arithmetic')
    return visit(ast.parse(expression, mode='eval').body)


SECTIONS = [('goal', 'Τι θα μάθεις'), ('prerequisites', 'Πριν ξεκινήσεις'),
            ('explanation', 'Κατανόησε την ιδέα'), ('example', 'Λυμένο παράδειγμα'),
            ('mistake', 'Συχνό λάθος'), ('recap', 'Κράτησε αυτό')]


def blocks_for(unit, entry):
    blocks = [{'title': title, 'content': '<p>' + escape(entry[key]).replace('\n', '</p><p>') + '</p>'}
              for key, title in SECTIONS]
    diagrams = {('gym-a', 'A', '2.1'): ('fraction-three-quarters.svg', 'Τρία από τέσσερα ίσα μέρη χρωματισμένα'),
                ('gym-a', 'B', '2.1'): ('axis-reflection.svg', 'Συμμετρικά σημεία Α και Α΄ σε ίσες κάθετες αποστάσεις από τον άξονα'),
                ('gym-b', 'B', '1.4'): ('pythagoras-5-12-13.svg', 'Ορθογώνιο τρίγωνο με κάθετες πλευρές 5 και 12 και υποτείνουσα 13'),
                ('gym-b', 'A', '3.4'): ('line-two-x-plus-three.svg', 'Γραφική παράσταση y=2x+3 με σημεία (0,3), (1,5), (3,9)'),
                ('gym-c', 'A', '3.2'): ('system-intersection.svg', 'Οι ευθείες x+y=5 και x−y=1 τέμνονται στο (3,2)'),
                ('gym-c', 'B', '1.3'): ('thales-triangle.svg', 'Τρίγωνο ΑΒΓ με ΔΕ παράλληλη στη ΒΓ και ανάλογα αντίστοιχα τμήματα'),
                ('alg-a', None, '4.2'): ('quadratic-sign-chart.svg', 'Το x²−5x+6 είναι θετικό έξω από τις ρίζες 2,3, αρνητικό ανάμεσά τους και μηδέν στις ρίζες'),
                ('geo-a', None, '3.15'): ('equal-tangents.svg', 'Οι εφαπτόμενες ΡΑ και ΡΒ από το ίδιο εξωτερικό σημείο είναι ίσες'),
                ('geo-a', None, '5.7'): ('centroid-ratio.svg', 'Οι διάμεσοι τέμνονται στο G και ΑG=2GΜ'),
                ('geo-a', None, '5.10'): ('trapezoid-midline.svg', 'Τραπέζιο με βάσεις 14 και 8 και διάμεσο 11, ενδεικτικό σχήμα'),
                ('orient-b', None, '1.2'): ('vector-triangle.svg', 'Πρόσθεση διανυσμάτων ως διαδοχικές μετατοπίσεις 3 και 4 με συνισταμένη μέτρου 5'),
                ('orient-b', None, '3.2'): ('parabola-focus-directrix.svg', 'Παραβολή y²=4x με εστία (1,0), διευθετούσα x=−1 και σημείο (1,2)'),
                ('orient-b', None, '3.3'): ('ellipse-focal-sum.svg', 'Έλλειψη x²/25+y²/16=1 με εστίες (−3,0),(3,0) και σταθερό άθροισμα αποστάσεων 10')}
    diagrams.update({
        ('geo-b', None, '9.2'): ('right-triangle-projections.svg', 'Ορθογώνιο τρίγωνο με κάθετες 6,8, υποτείνουσα 10, ύψος 4,8 και προβολές 3,6 και 6,4'),
        ('geo-b', None, '11.7'): ('sector-and-segment.svg', 'Τομέας 90° ακτίνας 4 με εμβαδόν 4π και μικρό κυκλικό τμήμα εμβαδού 4π−8')})
    diagrams.update({
        ('prob-stat', None, '2.7'): ('scatter-perfect-line.svg', 'Τέσσερα ζεύγη στην ευθεία y=2x+1 με r=1, χωρίς συμπέρασμα αιτιότητας'),
        ('analysis', None, '3.7'): ('area-line-parabola.svg', 'Το χωρίο μεταξύ y=x και y=x² στο [0,1] έχει εμβαδόν 1/6')})
    diagrams.update({('epal-math-stat', None, '2.2'):
        ('equal-width-histogram.svg', 'Ιστόγραμμα κλάσεων ίσου πλάτους 10 με συχνότητες 2,3,5 και συνολικά 10 παρατηρήσεις')})
    diagram = diagrams.get((unit['book_id'], unit['textbook_scope']['part'], unit['reference']))
    if diagram:
        filename, alt = diagram
        blocks.insert(3, {'title': 'Δες το στο σχήμα', 'content':
            '<img src="/static/images/theory/' + filename + '" alt="' + escape(alt, quote=True) +
            '" width="600" height="220" style="max-width:100%;height:auto;background:#fff;border-radius:12px">'})
    scope_note = entry.get('scope_note', '')
    if unit['exam_scope'] == 'excluded_bridge':
        scope_note = 'Μεταβατική ενότητα από το βιβλίο Α΄ Γυμνασίου: διδάσκεται στη Β΄ αλλά δεν αποτελεί εξεταστέα ύλη. ' + scope_note
    if scope_note:
        blocks.insert(0, {'title': 'Θέση στην ύλη', 'content': '<p>' + escape(scope_note) + '</p>'})
    refs = '; '.join(f"Οδηγίες ΙΕΠ, σελ. PDF {r.get('pdf_page', '—')}, §{unit['reference']}"
                     for r in unit['source_refs'])
    blocks.append({'title': 'Πηγές και επιμέλεια', 'content': '<p>' + escape(
        'Πρωτότυπη διατύπωση MathsFlow. Αντιστοίχιση: ' + refs +
        '. Οδηγίες διδασκαλίας 2026–2027 και σχολικό βιβλίο. Εκκρεμεί έλεγχος εκπαιδευτικού.'
        + (' Προαιρετική ενότητα.' if unit['teaching_scope'] == 'optional' else '')) + '</p>'})
    sources = {s['id']: s for s in json.loads((ROOT / 'curriculum/sources.json').read_text(encoding='utf-8'))}
    catalog = json.loads((ROOT / 'curriculum/catalog-2026-2027.json').read_text(encoding='utf-8'))
    book = next(b for b in catalog['books'] if b['id'] == unit['book_id'])
    url = sources[book['source_id']]['url']
    if not url.startswith('https://'):
        raise ValueError('Book source must use HTTPS')
    blocks[-1]['content'] += '<p><a href="' + escape(url, quote=True) + '">Ψηφιακό σχολικό βιβλίο</a></p>'
    return blocks


def validate_release(release):
    catalog = json.loads((ROOT / 'curriculum/catalog-2026-2027.json').read_text(encoding='utf-8'))
    courses = {c['key']: c for c in catalog['courses']}
    if release.get('schema_version') != 1 or release.get('course') not in courses:
        raise ValueError('Unknown release schema/course')
    course = courses[release['course']]
    units = {u['reference']: u for u in catalog['units'] if u['course_id'] == course['id']}
    entries = release.get('entries', [])
    if not entries or len({e['reference'] for e in entries}) != len(entries):
        raise ValueError('Empty release or duplicate reference')
    result = []
    for entry in entries:
        unit = units.get(entry['reference'])
        if not unit or 'expected_current' not in entry:
            raise ValueError('Unknown unit or missing explicit baseline')
        for key, _ in SECTIONS:
            value = entry.get(key)
            if not isinstance(value, str) or len(value.strip()) < 20 or '\ufffd' in value:
                raise ValueError('Missing/invalid section: ' + key)
            if value.count('\\(') != value.count('\\)') or value.count('\\[') != value.count('\\]'):
                raise ValueError('Unbalanced mathematics delimiters')
        checks = entry.get('checks')
        if not isinstance(checks, list) or not checks:
            raise ValueError('Every example needs arithmetic checks')
        for assertion in checks:
            left, relation, right = assertion
            a, b = arithmetic(left), arithmetic(right)
            if relation not in ('=', '<', '>') or not {'=': a == b, '<': a < b, '>': a > b}[relation]:
                raise ValueError('Failed example check: ' + str(assertion))
        result.append((unit, entry, blocks_for(unit, entry)))
    return result


def apply_release(connection, release):
    prepared = validate_release(release)
    connection.execute('BEGIN IMMEDIATE')
    try:
        changed = 0
        for unit, entry, blocks in prepared:
            desired = stable('theory-version/' + unit['id'] + '/' + digest(blocks))
            row = connection.execute('SELECT version_id FROM current_theory WHERE unit_id=?', (unit['id'],)).fetchone()
            current = row[0] if row else None
            if current == desired:
                continue
            if current != entry['expected_current']:
                raise ValueError('Theory changed since release baseline: ' + unit['reference'])
            add_theory_version(connection, unit['id'], blocks)
            changed += 1
        connection.commit()
        return changed
    except Exception:
        connection.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'apply'])
    parser.add_argument('release', type=Path)
    parser.add_argument('--database', type=Path, default=DEFAULT_PATH)
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    release = json.loads(args.release.read_text(encoding='utf-8'))
    prepared = validate_release(release)
    if args.action == 'check':
        print(f'Validated {len(prepared)} units; educator review pending.')
        return
    if not args.backup:
        parser.error('apply requires --backup pointing to a new file')
    copy_database(args.database, args.backup)
    connection = connect(args.database)
    try:
        print(f'Applied {apply_release(connection, release)} theory revisions.')
    finally:
        connection.close()


if __name__ == '__main__':
    main()
