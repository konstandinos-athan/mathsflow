import json,re,time,sqlite3
from pathlib import Path
from unittest.mock import patch
from werkzeug.datastructures import MultiDict
from tests.support import DatabaseCase
from app import create_app
from database import connect,copy_database

class AuthTests(DatabaseCase):
    password='correct horse battery SAMPLE'
    def setUp(self):
        super().setUp()
        self.app.config['AUTH_ENABLED']=True

    def csrf(self,client,path):
        page=client.get(path)
        self.assertEqual(page.status_code,200)
        return re.search(rb'name="csrf" value="([^"]+)"',page.data)[1].decode()

    def register(self,client=None,name='student_1'):
        client=client or self.client
        token=self.csrf(client,'/account/register')
        response=client.post('/account/register',data=dict(csrf=token,username=name,password=self.password,confirm=self.password,age_15='yes',privacy='yes'))
        self.assertEqual(response.status_code,200,response.data.decode())
        code=re.search(rb'<code class="recovery-code">([^<]+)</code>',response.data)[1].decode()
        return code

    def login(self,client=None,name='student_1',password=None):
        client=client or self.client
        return client.post('/account/login',data=dict(csrf=self.csrf(client,'/account/login'),username=name,password=password or self.password))

    def test_register_private_profile_hashing_and_no_secret_in_database_or_cookie(self):
        code=self.register()
        row=self.db.execute('SELECT * FROM users').fetchone()
        self.assertEqual(row['role'],'student');self.assertTrue(row['password_hash'].startswith('scrypt:'))
        text=' '.join(str(tuple(r)) for r in self.db.execute('SELECT * FROM account_security'))
        self.assertNotIn(code,text);self.assertNotIn(self.password,row['password_hash'])
        with self.client.session_transaction() as s:
            self.assertNotIn(code,str(dict(s)));self.assertNotIn(self.password,str(dict(s)))
        page=self.client.get('/account');self.assertEqual(page.status_code,200)
        self.assertIn(b'student_1',page.data);self.assertEqual(page.headers['Cache-Control'],'no-store')
        self.assertEqual(self.app.test_client().get('/account').status_code,401)

    def test_age_privacy_and_password_required_no_account_on_error(self):
        token=self.csrf(self.client,'/account/register')
        base=dict(csrf=token,username='student_1',password=self.password,confirm=self.password,age_15='yes',privacy='yes')
        for overrides in [{'age_15':'no'},{'privacy':'no'},{'password':'short'},{'username':'<script>'}]:
            self.assertEqual(self.client.post('/account/register',data={**base,**overrides}).status_code,400)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)

    def test_csrf_and_duplicate_fields_rejected(self):
        token=self.csrf(self.client,'/account/login')
        for data in [dict(username='test',password=self.password),dict(csrf='bad',username='test',password=self.password),MultiDict([('csrf',token),('username','a'),('username','b')])]:
            self.assertEqual(self.client.post('/account/login',data=data).status_code,400)
        other=self.app.test_client()
        self.assertEqual(other.post('/account/login',data=dict(csrf=token,username='test',password=self.password)).status_code,400)

    def test_logout_revokes_copied_session(self):
        self.register();copied=self.client.get_cookie('session').value
        token=self.csrf(self.client,'/account')
        self.assertEqual(self.client.post('/account/logout',data={'csrf':token}).status_code,302)
        other=self.app.test_client();other.set_cookie('session',copied)
        self.assertEqual(other.get('/account').status_code,401)
        self.assertEqual(self.client.get('/account/logout').status_code,405)

    def test_recovery_is_single_use_and_revokes_all_sessions(self):
        code=self.register();other=self.app.test_client();self.assertEqual(self.login(other).status_code,302)
        recovery_client=self.app.test_client();token=self.csrf(recovery_client,'/account/recover')
        password='another long secret password 123'
        response=recovery_client.post('/account/recover',data=dict(csrf=token,username='student_1',recovery=code,password=password,confirm=password))
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get('/account').status_code,401);self.assertEqual(other.get('/account').status_code,401)
        token=self.csrf(recovery_client,'/account/recover')
        self.assertEqual(recovery_client.post('/account/recover',data=dict(csrf=token,username='student_1',recovery=code,password=password,confirm=password)).status_code,400)
        self.assertEqual(self.login(recovery_client,password=password).status_code,302)

    def test_password_change_requires_old_password_and_rotates_sessions(self):
        self.register();other=self.app.test_client();self.login(other)
        token=self.csrf(self.client,'/account/password');password='replacement long password abc'
        form=dict(csrf=token,current_password='wrong',password=password,confirm=password)
        self.assertEqual(self.client.post('/account/password',data=form).status_code,400)
        self.assertEqual(self.client.post('/account/password',data={**form,'current_password':self.password}).status_code,200)
        self.assertEqual(other.get('/account').status_code,401)
        self.assertEqual(self.client.get('/account').status_code,200)

    def test_rate_limit_survives_new_client(self):
        for _ in range(5):
            self.assertEqual(self.login(name='unknown').status_code,400)
        self.assertEqual(self.login(self.app.test_client(),name='unknown').status_code,429)
        rows=[tuple(r) for r in self.db.execute('SELECT * FROM auth_limits')]
        self.assertNotIn('unknown',str(rows));self.assertNotIn('127.0.0.1',str(rows))
        with patch('auth.time.time',return_value=time.time()+901):
            self.assertNotEqual(self.login(self.app.test_client(),name='unknown').status_code,429)

    def quiz(self):
        url='/quiz/gel/a-gel/algebra/1'
        page=self.client.get(url)
        token=re.search(rb'name="attempt_token" value="([^"]+)"',page.data)[1].decode()
        self.assertEqual(self.client.post(url,data={'attempt_token':token}).status_code,200)
        return token,self.signer.loads(token)['attempt_id']

    def test_attempts_owned_and_other_users_cannot_read_result(self):
        self.register();token,aid=self.quiz()
        uid=self.db.execute('SELECT id FROM users').fetchone()[0]
        self.assertEqual(self.repo.attempt(aid)['user_id'],uid)
        result='/quiz/result/'+token
        self.assertEqual(self.client.get(result).status_code,200)
        other=self.app.test_client();self.assertEqual(other.get(result).status_code,404)
        self.register(other,'student_2');self.assertEqual(other.get(result).status_code,404)
        self.assertEqual(other.post('/quiz/gel/a-gel/algebra/1',data={'attempt_token':token}).status_code,400)

    def test_anonymous_quiz_token_is_session_bound(self):
        token,aid=self.quiz()
        other=self.app.test_client()
        self.assertEqual(other.post('/quiz/gel/a-gel/algebra/1',data={'attempt_token':token}).status_code,400)
        self.assertIsNone(self.repo.attempt(aid)['user_id'])

    def test_delete_removes_owned_data_and_preserves_other_users(self):
        self.register();token,aid=self.quiz()
        with self.assertRaises(sqlite3.IntegrityError):self.db.execute('DELETE FROM responses WHERE attempt_id=?',(aid,))
        self.db.rollback()
        other=self.app.test_client();self.register(other,'other_student')
        csrf=self.csrf(self.client,'/account/delete')
        self.assertEqual(self.client.post('/account/delete',data=dict(csrf=csrf,current_password=self.password,confirmation='wrong')).status_code,400)
        response=self.client.post('/account/delete',data=dict(csrf=csrf,current_password=self.password,confirmation='ΔΙΑΓΡΑΦΗ'))
        self.assertEqual(response.status_code,200)
        self.assertIsNone(self.repo.attempt(aid))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM responses').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM account_deletions').fetchone()[0],0)
        self.assertEqual(other.get('/account').status_code,200)

    def test_default_disabled_and_production_requires_storage_and_privacy(self):
        base=dict(TESTING=True,DATABASE=str(self.path),SECRET_KEY='test-only-key')
        disabled=create_app(base).test_client()
        self.assertEqual(disabled.get('/account/register').status_code,404)
        self.assertEqual(disabled.get('/').status_code,200)
        with self.assertRaises(RuntimeError):create_app({**base,'PRODUCTION':True,'AUTH_ENABLED':True})
        configured=create_app({**base,'PRODUCTION':True,'AUTH_ENABLED':True,'AUTH_PERSISTENT_STORAGE':True,'PRIVACY_CONTROLLER':'Test only','PRIVACY_CONTACT':'test@example.invalid'})
        self.assertTrue(configured.config['SESSION_COOKIE_SECURE'])
        self.assertTrue(configured.config['SESSION_COOKIE_HTTPONLY'])
        self.assertEqual(configured.config['SESSION_COOKIE_SAMESITE'],'Lax')

    def test_account_survives_app_restart_and_backup_restore(self):
        self.register();backup=Path(self.tmp.name)/'account-backup.sqlite3';copy_database(self.path,backup)
        new=create_app(dict(TESTING=True,AUTH_ENABLED=True,DATABASE=str(backup),SECRET_KEY='test-only-key'))
        client=new.test_client();token=self.csrf(client,'/account/login')
        self.assertEqual(client.post('/account/login',data=dict(csrf=token,username='student_1',password=self.password)).status_code,302)
        self.assertEqual(client.get('/account').status_code,200)

    def test_expired_session_denied(self):
        self.register()
        self.db.execute('UPDATE auth_sessions SET expires_at=?',(time.time()-1,));self.db.commit()
        self.assertEqual(self.client.get('/account').status_code,401)

    def test_privileged_role_input_cannot_create_admin(self):
        token=self.csrf(self.client,'/account/register')
        response=self.client.post('/account/register',data=dict(csrf=token,username='student_1',password=self.password,confirm=self.password,age_15='yes',privacy='yes',role='admin'))
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.db.execute('SELECT role FROM users').fetchone()[0],'student')

    def test_two_simultaneous_recoveries_consume_code_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        code=self.register();barrier=Barrier(2)
        def recover_once(number):
            client=self.app.test_client();token=self.csrf(client,'/account/recover')
            password='concurrent replacement password '+str(number)
            barrier.wait(timeout=10)
            return client.post('/account/recover',data=dict(csrf=token,username='student_1',recovery=code,password=password,confirm=password)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(recover_once,[1,2]))
        self.assertEqual(sorted(results),[200,400])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM auth_sessions').fetchone()[0],0)

    def test_simultaneous_registration_keeps_single_identity(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier=Barrier(2)
        def register_once(number):
            client=self.app.test_client();token=self.csrf(client,'/account/register')
            barrier.wait(timeout=10)
            return client.post('/account/register',data=dict(csrf=token,username='same_student',password=self.password,confirm=self.password,age_15='yes',privacy='yes')).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(register_once,[1,2]))
        self.assertEqual(sorted(results),[200,400])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],1)
