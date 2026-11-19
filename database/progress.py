"""Read-only progress derived from immutable, owned, submitted attempts."""
import json
from datetime import datetime, timezone


def date_label(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime('%d/%m/%Y %H:%M UTC')


def student_progress(db, user_id, page=1):
    count = db.execute('SELECT COUNT(*) FROM quiz_attempts WHERE user_id=? AND submitted_at IS NOT NULL',
                       (user_id,)).fetchone()[0]
    pages = max(1, (count + 19) // 20)
    page = min(page, pages)
    history = [dict(row) for row in db.execute('''SELECT a.id,a.unit_id,a.score,a.total,a.mode,a.difficulty,
        a.submitted_at,u.title,c.title AS course,g.title AS grade FROM quiz_attempts a
        JOIN units u ON u.id=a.unit_id JOIN courses c ON c.id=u.course_id JOIN grades g ON g.id=c.grade_id
        WHERE a.user_id=? AND a.submitted_at IS NOT NULL
        ORDER BY a.submitted_at DESC,a.id DESC LIMIT 20 OFFSET ?''', (user_id, (page-1)*20))]
    for item in history:
        item['date'] = date_label(item['submitted_at'])
        item['out_of_twenty'] = round(20 * item['score'] / item['total'], 1)

    # Collapse repeated versions of a question before selecting five distinct questions.
    evidence = db.execute('''WITH latest AS (
        SELECT a.unit_id,v.question_id,v.payload,r.correct,r.selected,a.submitted_at,a.id,
        ROW_NUMBER() OVER (PARTITION BY v.question_id ORDER BY a.submitted_at DESC,a.id DESC) AS latest
        FROM quiz_attempts a JOIN attempt_questions aq ON aq.attempt_id=a.id
        JOIN question_versions v ON v.id=aq.version_id
        JOIN responses r ON r.attempt_id=aq.attempt_id AND r.position=aq.position
        WHERE a.user_id=? AND a.submitted_at IS NOT NULL
    ), ranked AS (
        SELECT o.id AS objective_id,l.correct,l.selected,l.submitted_at,
        ROW_NUMBER() OVER (PARTITION BY o.id ORDER BY l.submitted_at DESC,l.id DESC,l.question_id) AS recent
        FROM latest l JOIN objectives o ON o.unit_id=l.unit_id
        WHERE l.latest=1 AND EXISTS (
            SELECT 1 FROM json_each(l.payload,'$.objective_ids') j WHERE j.value=o.id)
    ) SELECT objective_id,COUNT(*) AS samples,SUM(correct) AS correct,
        SUM(CASE WHEN selected IS NULL THEN 1 ELSE 0 END) AS unanswered,MAX(submitted_at) AS updated_at
        FROM ranked WHERE recent<=5 GROUP BY objective_id''', (user_id,)).fetchall()
    by_id = {row['objective_id']: dict(row) for row in evidence}
    objectives = []
    for row in db.execute('''SELECT o.id,o.unit_id,o.payload,u.title,c.title AS course,g.title AS grade
        FROM objectives o JOIN units u ON u.id=o.unit_id JOIN courses c ON c.id=u.course_id
        JOIN grades g ON g.id=c.grade_id WHERE EXISTS (
            SELECT 1 FROM quiz_attempts a WHERE a.user_id=? AND a.unit_id=u.id AND a.submitted_at IS NOT NULL)
        ORDER BY g.rowid,c.rowid,u.display_order,o.id''', (user_id,)):
        item = dict(row)
        item['text'] = json.loads(item.pop('payload'))['text']
        item.update(by_id.get(item['id'], dict(samples=0, correct=0, unanswered=0, updated_at=None)))
        item['wrong'] = item['samples'] - item['correct'] - item['unanswered']
        item['percent'] = round(100 * item['correct'] / item['samples']) if item['samples'] else None
        item['status'] = ('Δεν υπάρχουν στοιχεία' if not item['samples'] else
                          'Λίγα στοιχεία' if item['samples'] < 3 else
                          'Καλή πρόσφατη επίδοση' if item['correct'] / item['samples'] >= .8 else
                          'Χρειάζεται επανάληψη')
        objectives.append(item)
    recommendations = sorted(
        [o for o in objectives if o['samples'] and o['correct'] < o['samples']],
        key=lambda o: (-(o['samples']-o['correct']) / o['samples'], o['updated_at'], o['id']))[:5]
    return dict(history=history, count=count, page=page, pages=pages, objectives=objectives,
                recommendations=recommendations, covered=sum(o['samples'] > 0 for o in objectives))
