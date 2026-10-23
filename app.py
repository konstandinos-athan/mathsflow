"""MathsFlow web application. Runtime educational data is read from SQLite."""
import os
import secrets
from flask import Flask, abort, g, render_template, request, send_from_directory
from itsdangerous import BadSignature, URLSafeTimedSerializer
from database import DEFAULT_PATH, connect
from database.repository import Repository


def create_app(config=None):
    application = Flask(__name__, template_folder='templates')
    if os.environ.get('MATHSFLOW_ENV') == 'production' and not os.environ.get('SECRET_KEY'):
        raise RuntimeError('SECRET_KEY is required in production')
    application.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
                              DATABASE=os.environ.get('MATHSFLOW_DATABASE', str(DEFAULT_PATH)))
    if config:
        application.config.update(config)
    signer = URLSafeTimedSerializer(application.secret_key, salt='quiz-attempt-v2')
    application.extensions['quiz_signer'] = signer

    def repository():
        if 'database' not in g:
            g.database = connect(application.config['DATABASE'])
        return Repository(g.database)

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
        return render_template('study/study.html', **context(unit), theoria=repository().theory(unit['id']))

    @application.route('/study/<school_key>/<class_key>/<subject_key>/<int:lesson_id>')
    def study(school_key, class_key, subject_key, lesson_id):
        return show_study(require_unit(repository().legacy_unit(school_key, class_key, subject_key, lesson_id)))

    @application.route('/study/unit/<uuid:unit_id>')
    def study_unit(unit_id):
        return show_study(require_unit(repository().unit(str(unit_id))))

    def show_quiz(unit):
        difficulty = (request.form if request.method == 'POST' else request.args).get('difficulty', 'all')
        if difficulty not in ('all', 'easy', 'medium', 'hard'):
            abort(400)
        repo = repository()
        if request.method == 'GET':
            attempt = repo.start_attempt(unit['id'], difficulty)
            token = signer.dumps({'attempt_id': attempt['id'], 'unit_id': unit['id'], 'difficulty': difficulty}) if attempt else ''
        else:
            token = request.form.get('attempt_token', '')
            try:
                payload = signer.loads(token, max_age=7200)
            except BadSignature:
                abort(400, description='Το κουίζ έληξε ή δεν είναι έγκυρο. Ανοίξτε το ξανά.')
            if not isinstance(payload, dict) or payload.get('unit_id') != unit['id'] or payload.get('difficulty') != difficulty or not isinstance(payload.get('attempt_id'), str):
                abort(400)
            try:
                attempt = repo.submit_attempt(payload['attempt_id'], unit['id'], difficulty, request.form)
            except ValueError:
                abort(400, description='Η προσπάθεια δεν είναι έγκυρη ή έχει λήξει. Ανοίξτε το κουίζ ξανά.')
        return render_template('quiz/quiz.html', **context(unit), difficulty=difficulty,
                               questions=attempt['questions'] if attempt else [], score=attempt['score'] if attempt else None,
                               total=attempt['total'] if attempt else 0, user_answers=attempt['user_answers'] if attempt else {},
                               attempt_token=token)

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
