"""Optional accounts. Public activation is gated on persistent storage and privacy details."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid
from datetime import timedelta
from flask import abort, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash


def install_auth(app, repository):
    app.config.setdefault('AUTH_ENABLED', False)
    app.config.setdefault('AUTH_PERSISTENT_STORAGE', False)
    app.config.setdefault('PRIVACY_CONTROLLER', '')
    app.config.setdefault('PRIVACY_CONTACT', '')
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
    if app.config.get('PRODUCTION'):
        app.config['SESSION_COOKIE_SECURE'] = True
        if app.config['AUTH_ENABLED'] and not all(app.config.get(k) for k in (
            'AUTH_PERSISTENT_STORAGE', 'PRIVACY_CONTROLLER', 'PRIVACY_CONTACT')):
            raise RuntimeError('Accounts require verified persistent storage and completed privacy details')
    dummy = generate_password_hash('dummy-login-value-not-an-account', method='scrypt')

    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def csrf():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        return session['csrf']

    def enabled():
        if not app.config['AUTH_ENABLED']:
            abort(404)

    def db():
        return repository().db

    def require_user():
        enabled()
        if g.user is None:
            abort(401)
        return g.user

    @app.before_request
    def load_identity():
        g.user = None
        if not app.config['AUTH_ENABLED']:
            return
        raw = session.get('auth_token')
        if isinstance(raw, str):
            row = db().execute('''SELECT u.id,u.username,u.role FROM auth_sessions s
                JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?''',
                (digest(raw), time.time())).fetchone()
            if row:
                g.user = dict(row)
            else:
                session.pop('auth_token', None)
        if request.path.startswith('/account') and request.method == 'POST':
            if any(len(request.form.getlist(k)) != 1 for k in request.form):
                abort(400)
            value = request.form.get('csrf', '')
            if not session.get('csrf') or not hmac.compare_digest(value, session['csrf']):
                abort(400, description='Η φόρμα έληξε. Άνοιξέ τη ξανά.')

    @app.errorhandler(401)
    @app.errorhandler(429)
    def account_access_error(error):
        if not request.path.startswith('/account'):
            return error
        message = ('Συνδέσου για να ανοίξεις τον λογαριασμό σου.' if error.code == 401 else
                   'Πολλές προσπάθειες. Περίμενε λίγο πριν δοκιμάσεις ξανά.')
        return render_template('account/error.html', message=message), error.code

    @app.context_processor
    def auth_context():
        return dict(current_user=getattr(g, 'user', None), accounts_enabled=app.config['AUTH_ENABLED'], csrf_token=csrf)

    @app.after_request
    def auth_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        # Baseline restrictions compatible with existing inline MathJax/configuration.
        # This is not a strict script-src policy or a replacement for HTML sanitization.
        response.headers['Content-Security-Policy'] = "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'"
        if app.config.get('PRODUCTION'):
            response.headers['Strict-Transport-Security'] = 'max-age=86400'
        if getattr(g, 'user', None) is not None or request.path.startswith('/account') or request.path.startswith('/quiz/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    def throttle(scope, username, maximum=5, window=900):
        # Never trust a client-provided forwarding header as an IP address.
        # The account limit works across all IPs and workers; the IP bucket is deliberately broader.
        now = time.time()
        keys = [(scope+':name:'+username, maximum), (scope+':ip:'+str(request.remote_addr), 60)]
        conn = db()
        conn.execute('BEGIN IMMEDIATE')
        try:
            conn.execute('DELETE FROM auth_limits WHERE expires_at<=?', (now,))
            conn.execute('DELETE FROM auth_sessions WHERE expires_at<=?', (now,))
            for raw, limit in keys:
                key = hmac.new(app.secret_key.encode() if isinstance(app.secret_key,str) else app.secret_key, raw.encode(), hashlib.sha256).hexdigest()
                row=conn.execute('SELECT hits FROM auth_limits WHERE key=?',(key,)).fetchone()
                if row and row['hits'] >= limit:
                    conn.rollback()
                    abort(429, description='Πολλές προσπάθειες. Δοκίμασε αργότερα.')
                conn.execute('''INSERT INTO auth_limits(key,hits,expires_at) VALUES (?,1,?)
                    ON CONFLICT(key) DO UPDATE SET hits=hits+1''',(key,now+window))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def identity_input():
        value = request.form.get('username','').strip().lower()
        if not re.fullmatch(r'[a-z0-9_]{3,32}',value):
            return None
        return value

    def valid_password(value, username):
        if not 15 <= len(value) <= 128 or value.isspace():
            return False
        compact=value.lower().replace(' ','')
        common={'passwordpassword','123456789012345','12345678901234567890','qwertyuiopasdfgh','letmeinletmeinletmein'}
        return compact not in common and len(set(value))>=4 and compact!=username

    def login_user(conn, user_id):
        # Rotate both the authentication capability and CSRF token on login/reset/change.
        old=session.get('auth_token')
        if isinstance(old,str):
            conn.execute('DELETE FROM auth_sessions WHERE token_hash=?',(digest(old),))
        token=secrets.token_urlsafe(32)
        conn.execute('INSERT INTO auth_sessions VALUES (?,?,?)',(digest(token),user_id,time.time()+43200))
        session.clear()
        session.permanent=True
        session['auth_token']=token
        csrf()

    def form(page, error=None, status=200, recovery=None):
        return render_template('account/form.html',page=page,error=error,recovery=recovery),status

    @app.route('/account/register',methods=['GET','POST'])
    def register():
        enabled()
        if request.method=='GET':return form('register')
        username=identity_input()
        throttle('register',username or 'invalid',maximum=5,window=3600)
        password=request.form.get('password','')
        if not username:return form('register','Χρησιμοποίησε 3–32 λατινικά γράμματα, αριθμούς ή κάτω παύλα.',400)
        if request.form.get('age_15')!='yes' or request.form.get('privacy')!='yes':
            return form('register','Η αυτοτελής εγγραφή διατίθεται από 15 ετών. Μπορείς να συνεχίσεις χωρίς λογαριασμό.',400)
        if not valid_password(password,username) or password!=request.form.get('confirm'):
            return form('register','Διάλεξε κωδικό 15–128 χαρακτήρων και γράψε τον ίδιο και στα δύο πεδία.',400)
        recovery=secrets.token_urlsafe(24)
        password_hash=generate_password_hash(password,method='scrypt')
        conn=db();conn.execute('BEGIN IMMEDIATE')
        try:
            uid=str(uuid.uuid4())
            conn.execute('INSERT INTO users(id,username,password_hash,role,created_at) VALUES (?,?,?,?,?)',
                         (uid,username,password_hash,'student',time.time()))
            conn.execute('INSERT INTO account_security VALUES (?,?,?,?)',(uid,digest(recovery),'2026-11-18-draft-v2',time.time()))
            login_user(conn,uid)
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback();return form('register','Δεν μπορεί να χρησιμοποιηθεί αυτό το όνομα χρήστη.',400)
        except Exception:
            conn.rollback();raise
        g.user={'id':uid,'username':username,'role':'student'}
        return form('recovery_code',recovery=recovery)

    @app.route('/account/login',methods=['GET','POST'])
    def login():
        enabled()
        if request.method=='GET':return form('login')
        username=identity_input()
        throttle('login',username or 'invalid')
        row=db().execute('SELECT * FROM users WHERE username=?',(username or '',)).fetchone()
        password=request.form.get('password','')
        good=check_password_hash(row['password_hash'] if row else dummy,password[:129])
        if not row or len(password)>128 or not good:
            return form('login','Το όνομα χρήστη ή ο κωδικός δεν είναι σωστός.',400)
        conn=db();conn.execute('BEGIN IMMEDIATE')
        try:
            # Re-read inside the lock: recovery/deletion must not race this login.
            current=conn.execute('SELECT password_hash FROM users WHERE id=?',(row['id'],)).fetchone()
            if not current or current[0]!=row['password_hash']:
                conn.rollback();return form('login','Το όνομα χρήστη ή ο κωδικός δεν είναι σωστός.',400)
            login_user(conn,row['id']);conn.commit()
        except Exception:
            conn.rollback();raise
        return redirect(url_for('account'))

    @app.route('/account')
    def account():
        require_user()
        return form('profile')

    @app.route('/account/logout',methods=['POST'])
    def logout():
        require_user()
        db().execute('DELETE FROM auth_sessions WHERE token_hash=?',(digest(session['auth_token']),));db().commit()
        session.clear()
        return redirect(url_for('home'))

    @app.route('/account/recover',methods=['GET','POST'])
    def recover():
        enabled()
        if request.method=='GET':return form('recover')
        username=identity_input();throttle('recover',username or 'invalid')
        password=request.form.get('password','')
        if not valid_password(password,username or '') or password!=request.form.get('confirm'):
            return form('recover','Διάλεξε νέο κωδικό 15–128 χαρακτήρων και επιβεβαίωσέ τον.',400)
        password_hash=generate_password_hash(password,method='scrypt')
        new_code=secrets.token_urlsafe(24);conn=db();conn.execute('BEGIN IMMEDIATE')
        try:
            row=conn.execute('SELECT u.id,s.recovery_hash FROM users u JOIN account_security s ON s.user_id=u.id WHERE u.username=?',(username or '',)).fetchone()
            supplied=digest(request.form.get('recovery','').strip())
            if not row or not hmac.compare_digest(row['recovery_hash'],supplied):
                conn.rollback();return form('recover','Τα στοιχεία ανάκτησης δεν είναι σωστά.',400)
            conn.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash,row['id']))
            conn.execute('UPDATE account_security SET recovery_hash=? WHERE user_id=?',(digest(new_code),row['id']))
            conn.execute('DELETE FROM auth_sessions WHERE user_id=?',(row['id'],))
            conn.commit();session.clear();g.user=None
        except Exception:
            conn.rollback();raise
        return form('recovery_code',recovery=new_code)

    @app.route('/account/password',methods=['GET','POST'])
    def change_password():
        user=require_user()
        if request.method=='GET':return form('password')
        throttle('password',user['username'])
        password=request.form.get('password','')
        if not valid_password(password,user['username']) or password!=request.form.get('confirm'):
            return form('password','Διάλεξε νέο κωδικό 15–128 χαρακτήρων και επιβεβαίωσέ τον.',400)
        password_hash=generate_password_hash(password,method='scrypt');code=secrets.token_urlsafe(24)
        conn=db();conn.execute('BEGIN IMMEDIATE')
        try:
            row=conn.execute('SELECT password_hash FROM users WHERE id=?',(user['id'],)).fetchone()
            if not row or not check_password_hash(row[0],request.form.get('current_password','')[:129]):
                conn.rollback();return form('password','Ο τρέχων κωδικός δεν είναι σωστός.',400)
            conn.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash,user['id']))
            conn.execute('UPDATE account_security SET recovery_hash=? WHERE user_id=?',(digest(code),user['id']))
            conn.execute('DELETE FROM auth_sessions WHERE user_id=?',(user['id'],))
            login_user(conn,user['id']);conn.commit()
        except Exception:
            conn.rollback();raise
        return form('recovery_code',recovery=code)

    @app.route('/account/export', methods=['GET', 'POST'])
    def export_account():
        user = require_user()
        if request.method == 'GET':
            return render_template('account/export.html')
        throttle('export', user['username'])
        conn = db()
        # One read snapshot; never accept a client-supplied user/attempt identifier.
        conn.execute('BEGIN')
        try:
            row = conn.execute('SELECT password_hash FROM users WHERE id=?', (user['id'],)).fetchone()
            if not row or not check_password_hash(row[0], request.form.get('current_password', '')[:129]):
                conn.rollback()
                return render_template('account/export.html', error='Ο τρέχων κωδικός δεν είναι σωστός.'), 400

            def rows(sql):
                return [dict(item) for item in conn.execute(sql, (user['id'],))]

            payload = {
                'format_version': 1,
                'exported_at_unix': time.time(),
                'account': rows('SELECT id,username,role,created_at FROM users WHERE id=?')[0],
                'privacy_acknowledgement': rows('SELECT privacy_version,accepted_at FROM account_security WHERE user_id=?'),
                'attempts': rows('''SELECT id,unit_id,difficulty,mode,started_at,submitted_at,score,total
                    FROM quiz_attempts WHERE user_id=? ORDER BY started_at,id'''),
                'responses': rows('''SELECT r.attempt_id,r.position,r.selected,r.correct,q.version_id
                    FROM responses r JOIN quiz_attempts a ON a.id=r.attempt_id
                    JOIN attempt_questions q ON q.attempt_id=r.attempt_id AND q.position=r.position
                    WHERE a.user_id=? ORDER BY a.started_at,r.attempt_id,r.position'''),
                'stored_progress': rows('SELECT unit_id,mastery,updated_at FROM user_progress WHERE user_id=? ORDER BY unit_id'),
                'rewards': rows('SELECT event_id,reward_type,xp,created_at FROM reward_ledger WHERE user_id=? ORDER BY created_at,id'),
                'notes': 'Timestamps are Unix seconds. Dashboard progress and levels are derived from responses and rewards. Password hashes, recovery secrets and session tokens are deliberately excluded. Provider logs and backups are not included.'
            }
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        response = jsonify(payload)
        response.headers['Content-Disposition'] = 'attachment; filename="mathsflow-data.json"'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/account/delete',methods=['GET','POST'])
    def delete_account():
        user=require_user()
        if request.method=='GET':return form('delete')
        throttle('delete',user['username'])
        conn=db();conn.execute('BEGIN IMMEDIATE')
        try:
            row=conn.execute('SELECT password_hash FROM users WHERE id=?',(user['id'],)).fetchone()
            if request.form.get('confirmation')!='ΔΙΑΓΡΑΦΗ' or not row or not check_password_hash(row[0],request.form.get('current_password','')[:129]):
                conn.rollback();return form('delete','Έλεγξε τον κωδικό και γράψε ΔΙΑΓΡΑΦΗ για επιβεβαίωση.',400)
            uid=user['id'];conn.execute('INSERT INTO account_deletions VALUES (?)',(uid,))
            for table in ('responses','attempt_questions'):
                conn.execute(f'DELETE FROM {table} WHERE attempt_id IN (SELECT id FROM quiz_attempts WHERE user_id=?)',(uid,))
            for table in ('quiz_attempts','user_progress','reward_ledger','auth_sessions','account_security'):
                conn.execute(f'DELETE FROM {table} WHERE user_id=?',(uid,))
            conn.execute('DELETE FROM users WHERE id=?',(uid,))
            conn.execute('DELETE FROM account_deletions WHERE user_id=?',(uid,))
            conn.commit();session.clear();g.user=None
        except Exception:
            conn.rollback();raise
        return form('deleted')

    @app.route('/account/privacy')
    def account_privacy():
        enabled()
        return render_template('account/privacy.html',controller=app.config['PRIVACY_CONTROLLER'],contact=app.config['PRIVACY_CONTACT'])
