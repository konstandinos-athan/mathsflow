from tests.test_auth import AuthTests
from tests.support import DatabaseCase


class ContactTests(DatabaseCase):
    password = AuthTests.password
    csrf = AuthTests.csrf
    register = AuthTests.register

    def test_owned_messages_admin_reply_and_export(self):
        self.app.config['AUTH_ENABLED'] = True
        self.register()
        token = self.csrf(self.client, '/account/contact')
        self.assertEqual(self.client.post('/account/contact', data={'csrf':token,'category':'privacy','message':'<script>test message</script>'}).status_code,302)
        self.assertIn(b'&lt;script&gt;',self.client.get('/account/contact').data)
        self.assertEqual(self.client.get('/account/admin/contact').status_code,403)
        other=self.app.test_client();self.register(other,'other_student')
        self.assertNotIn(b'test message',other.get('/account/contact').data)
        self.db.execute("UPDATE users SET role='admin' WHERE username='other_student'");self.db.commit()
        request_id=self.db.execute('SELECT id FROM contact_requests').fetchone()[0]
        token=self.csrf(other,'/account/admin/contact')
        self.assertEqual(other.post('/account/admin/contact',data={'csrf':token,'id':request_id,'reply':'Η απάντησή σου'}).status_code,302)
        self.assertIn('Η απάντησή σου'.encode(),self.client.get('/account/contact').data)
        response=self.client.post('/account/export',data={'csrf':self.csrf(self.client,'/account/export'),'current_password':self.password})
        self.assertEqual(len(response.json['contact_requests']),1)

    def test_gates_csrf_and_rate_limit(self):
        self.assertEqual(self.client.get('/account/contact').status_code,404)
        self.app.config['AUTH_ENABLED']=True
        self.assertEqual(self.client.get('/account/contact').status_code,401)
        self.register()
        self.assertEqual(self.client.post('/account/contact',data={'message':'example'}).status_code,400)
        token=self.csrf(self.client,'/account/contact')
        for i in range(4):
            response=self.client.post('/account/contact',data={'csrf':token,'category':'general','message':'test message here'})
        self.assertEqual(response.status_code,429)
