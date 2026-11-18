"""Versioned learning rewards, awarded inside the submission transaction."""
XP_PER_QUESTION = 10
XP_PER_LEVEL = 100
REWARD_TYPE = 'first_correct_v1'
BADGES = ((1, 'Πρώτο βήμα'), (10, 'Δέκα σωστές'),
          (50, 'Σταθερή εξάσκηση'), (100, 'Εκατό σωστές'))


def award_attempt(db, attempt_id):
    """Caller owns BEGIN IMMEDIATE; never commit independently of the grade."""
    db.execute('''INSERT INTO reward_ledger(id,user_id,event_id,reward_type,xp,created_at)
        SELECT lower(hex(randomblob(16))),a.user_id,v.question_id,?,?,a.submitted_at
        FROM quiz_attempts a JOIN responses r ON r.attempt_id=a.id
        JOIN attempt_questions aq ON aq.attempt_id=r.attempt_id AND aq.position=r.position
        JOIN question_versions v ON v.id=aq.version_id
        WHERE a.id=? AND a.user_id IS NOT NULL AND a.submitted_at IS NOT NULL AND r.correct=1
        ON CONFLICT(user_id,event_id,reward_type) DO NOTHING''',
        (REWARD_TYPE, XP_PER_QUESTION, attempt_id))


def rewards_summary(db, user_id):
    row = db.execute('''SELECT COUNT(*) AS questions,COALESCE(SUM(xp),0) AS xp
        FROM reward_ledger WHERE user_id=? AND reward_type=?''', (user_id, REWARD_TYPE)).fetchone()
    xp = row['xp']
    return dict(xp=xp, questions=row['questions'], level=1+xp//XP_PER_LEVEL,
                level_xp=xp % XP_PER_LEVEL, next_xp=XP_PER_LEVEL-xp % XP_PER_LEVEL,
                level_size=XP_PER_LEVEL,
                badges=[dict(threshold=n, title=title, earned=row['questions'] >= n)
                        for n, title in BADGES])
