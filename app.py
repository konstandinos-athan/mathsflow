"""MathsFlow web application. Runtime educational data is read from SQLite."""
import os
import json
import secrets
from flask import Flask, abort, g, render_template, request, send_from_directory, url_for, session
from itsdangerous import BadSignature, URLSafeTimedSerializer
from database import DEFAULT_PATH, connect
from database.repository import Repository
from account_config import account_environment


def create_app(config=None):
    application = Flask(__name__, template_folder='templates')
    if os.environ.get('MATHSFLOW_ENV') == 'production' and not os.environ.get('SECRET_KEY'):
        raise RuntimeError('SECRET_KEY is required in production')
    application.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
                              DATABASE=os.environ.get('DATABASE_URL') or os.environ.get('MATHSFLOW_DATABASE', str(DEFAULT_PATH)),
                              MAX_CONTENT_LENGTH=65536)
    application.config.update(account_environment())
    if config:
        application.config.update(config)
    application.config.setdefault('PRODUCTION', os.environ.get('MATHSFLOW_ENV') == 'production')
    signer = URLSafeTimedSerializer(application.secret_key, salt='quiz-attempt-v2')
    application.extensions['quiz_signer'] = signer

    def repository():
        if 'database' not in g:
            g.database = connect(application.config['DATABASE'])
        return Repository(g.database)

    from auth import install_auth
    install_auth(application, repository)

    @application.teardown_appcontext
    def close_database(error=None):
        connection = g.pop('database', None)
        if connection is not None:
            connection.close()

    def school_and_class(school_key, class_key=None):
        school = repository().navigation().get(school_key)
        if school is None:
            abort(404)
        if class_key is None:
            return school, None
        grade = school['classes'].get(class_key)
        if grade is None:
            abort(404)
        return school, grade

    def require_unit(unit):
        if unit is None:
            abort(404)
        return unit

    def context(unit):
        return dict(school_key=unit['school_key'], class_key=unit['class_key'],
                    subject_key=unit['subject_key'], school_name=unit['school_name'],
                    class_name=unit['class_name'], subject_name=unit['subject_name'], enotita=unit['title'])

    @application.route('/')
    def home():
        return render_template('index.html', schools=repository().navigation())

    @application.route('/favicon.ico')
    def favicon():
        return send_from_directory(application.static_folder, 'favicon.ico')

    @application.route('/privacy')
    def privacy_policy():
        return render_template('account/privacy.html', controller=application.config['PRIVACY_CONTROLLER'],
                               contact=application.config['PRIVACY_CONTACT'])

    @application.route('/cookies')
    def cookie_policy():
        return render_template('legal/cookies.html')

    @application.route('/terms')
    def terms_of_use():
        return render_template('legal/terms.html')

    @application.route('/ai-policy')
    def ai_policy():
        return render_template('legal/ai_policy.html')

    @application.route('/data-rights')
    def data_rights():
        return render_template('legal/data_rights.html')

    @application.route('/contact')
    def contact_page():
        return render_template('legal/contact.html', controller=application.config['PRIVACY_CONTROLLER'],
                               contact=application.config['PRIVACY_CONTACT'])

    @application.route('/accessibility')
    def accessibility_page():
        return render_template('legal/accessibility.html')

    @application.route('/school/<school_key>')
    def school_page(school_key):
        school, _ = school_and_class(school_key)
        return render_template('school.html', school_key=school_key, school_name=school['name'], classes=school['classes'])

    @application.route('/school/<school_key>/<class_key>')
    def class_page(school_key, class_key):
        school, grade = school_and_class(school_key, class_key)
        return render_template('class.html', school_key=school_key, class_key=class_key,
                               school_name=school['name'], class_name=grade['name'], subjects=grade['subjects'])

    @application.route('/school/<school_key>/<class_key>/<subject_key>')
    def subject_page(school_key, class_key, subject_key):
        school, grade = school_and_class(school_key, class_key)
        if (school_key, class_key, subject_key) == ('gel', 'g-gel', 'algebra'):
            subject_key = 'math-katefthinsis'
        subject = grade['subjects'].get(subject_key)
        if subject is None:
            abort(404)
        return render_template('subject.html', school_key=school_key, class_key=class_key,
                               subject_key=subject_key, school_name=school['name'], class_name=grade['name'],
                               subject_name=subject['name'], lessons=subject['lessons'])

    def show_study(unit):
        return render_template('study/study.html', needs_mathjax=True, **context(unit), theoria=repository().theory(unit['id']))

    @application.route('/study/<school_key>/<class_key>/<subject_key>/<int:lesson_id>')
    def study(school_key, class_key, subject_key, lesson_id):
        return show_study(require_unit(repository().legacy_unit(school_key, class_key, subject_key, lesson_id)))

    @application.route('/study/unit/<uuid:unit_id>')
    def study_unit(unit_id):
        return show_study(require_unit(repository().unit(str(unit_id))))

    def show_quiz(unit):
        values = request.form if request.method == 'POST' else request.args
        if any(len(values.getlist(key)) != 1 for key in values):
            abort(400)
        mode = values.get('mode', 'practice')
        if mode not in ('practice', 'exam'):
            abort(400)
        difficulty = values.get('difficulty', 'all')
        if difficulty not in ('all', 'easy', 'medium', 'hard'):
            abort(400)
        repo = repository()
        if request.method == 'GET':
            attempt = repo.start_attempt(unit['id'], difficulty, mode, user_id=g.user['id'] if g.user else None)
            if 'quiz_nonce' not in session:
                session['quiz_nonce'] = secrets.token_urlsafe(32)
            token = signer.dumps({'attempt_id': attempt['id'], 'unit_id': unit['id'], 'difficulty': difficulty, 'mode': mode, 'nonce': session['quiz_nonce'], 'owner': g.user['id'] if g.user else None}) if attempt else ''
        else:
            token = request.form.get('attempt_token', '')
            try:
                payload = signer.loads(token, max_age=7200)
            except BadSignature:
                abort(400, description='Το κουίζ έληξε ή δεν είναι έγκυρο. Ανοίξτε το ξανά.')
            if not isinstance(payload, dict) or payload.get('unit_id') != unit['id'] or payload.get('difficulty') != difficulty or payload.get('mode', 'practice') != mode or not isinstance(payload.get('attempt_id'), str):
                abort(400)
            if payload.get('nonce') != session.get('quiz_nonce') or not payload.get('nonce'):
                abort(400)
            owner = g.user['id'] if g.user else None
            if payload.get('owner') != owner:
                abort(403)
            stored = repo.attempt(payload['attempt_id'])
            if stored and stored['user_id'] != owner:
                abort(403)
            try:
                attempt = repo.submit_attempt(payload['attempt_id'], unit['id'], difficulty, request.form, mode)
            except ValueError:
                abort(400, description='Η προσπάθεια δεν είναι έγκυρη ή έχει λήξει. Ανοίξτε το κουίζ ξανά.')
        return render_attempt(unit, attempt, token, difficulty, mode)

    def render_attempt(unit, attempt, token, difficulty, mode):
        return render_template('quiz/quiz.html', needs_mathjax=True, **context(unit), difficulty=difficulty,
                               quiz_url=url_for('quiz_unit', unit_id=unit['id']), mode=mode, grading=attempt.get('grading') if attempt else None,
                               new_attempt_url=url_for('quiz_unit', unit_id=unit['id'], difficulty=difficulty, mode=mode),
                               result_url=url_for('quiz_result', token=token) if attempt and attempt['score'] is not None else None,
                               teaching_scope=json.loads(unit['payload']).get('teaching_scope'),
                               questions=attempt['questions'] if attempt else [], score=attempt['score'] if attempt else None,
                               total=attempt['total'] if attempt else 0, user_answers=attempt['user_answers'] if attempt else {},
                               attempt_token=token)

    @application.errorhandler(400)
    @application.errorhandler(413)
    def quiz_input_error(error):
        if request.path.startswith('/account'):
            return render_template('account/error.html', message='Η φόρμα δεν είναι έγκυρη ή έχει λήξει. Άνοιξέ τη ξανά.'), error.code
        if not request.path.startswith('/quiz/'):
            return error
        message = ('Η υποβολή είναι υπερβολικά μεγάλη.' if error.code == 413 else
                   'Η υποβολή δεν είναι έγκυρη ή η προσπάθεια έχει λήξει. Η βαθμολογία δεν άλλαξε.')
        return render_template('quiz/error.html', message=message), error.code

    @application.after_request
    def quiz_privacy(response):
        if request.path.startswith('/quiz/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @application.route('/quiz/result/<token>')
    def quiz_result(token):
        try:
            payload = signer.loads(token)
        except BadSignature:
            abort(404)
        if not isinstance(payload, dict) or not isinstance(payload.get('attempt_id'), str):
            abort(404)
        attempt = repository().attempt(payload['attempt_id'])
        if not attempt or attempt['score'] is None or any((
            payload.get('unit_id') != attempt['unit_id'],
            payload.get('difficulty') != attempt['difficulty'],
            payload.get('mode', 'practice') != attempt['mode'],
        )):
            abort(404)
        if attempt['user_id'] is not None and (not g.user or g.user['id'] != attempt['user_id']):
            abort(404)
        unit = require_unit(repository().unit(attempt['unit_id']))
        return render_attempt(unit, attempt, token, attempt['difficulty'], attempt['mode'])

    def progress_user():
        if not application.config['AUTH_ENABLED']:
            abort(404)
        if not g.user:
            abort(401)
        return g.user['id']

    @application.route('/account/progress')
    def account_progress():
        user_id = progress_user()
        values = request.args.getlist('page')
        if len(values) > 1 or (values and (not values[0].isascii() or not values[0].isdigit() or len(values[0]) > 9)):
            abort(400)
        page = int(values[0]) if values else 1
        if page < 1:
            abort(400)
        from database.progress import student_progress
        from database.rewards import rewards_summary
        return render_template('account/progress.html', rewards=rewards_summary(repository().db, user_id),
                               **student_progress(repository().db, user_id, page))

    @application.route('/account/attempt/<uuid:attempt_id>')
    def account_attempt(attempt_id):
        user_id = progress_user()
        attempt = repository().attempt(str(attempt_id))
        if not attempt or attempt['user_id'] != user_id or attempt['submitted_at'] is None:
            abort(404)
        token = signer.dumps({key: attempt[key] for key in ('unit_id', 'difficulty', 'mode')} | {'attempt_id': attempt['id']})
        return render_attempt(require_unit(repository().unit(attempt['unit_id'])), attempt, token,
                              attempt['difficulty'], attempt['mode'])

    @application.route('/quiz/<school_key>/<class_key>/<subject_key>/<int:lesson_id>', methods=['GET', 'POST'])
    def quiz(school_key, class_key, subject_key, lesson_id):
        return show_quiz(require_unit(repository().legacy_unit(school_key, class_key, subject_key, lesson_id)))

    @application.route('/quiz/unit/<uuid:unit_id>', methods=['GET', 'POST'])
    def quiz_unit(unit_id):
        return show_quiz(require_unit(repository().unit(str(unit_id))))

    return application


app = create_app()
quiz_signer = app.extensions['quiz_signer']

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=os.environ.get('FLASK_DEBUG') == '1')
