import io
from pathlib import Path
import tempfile
import unittest
from serving import create_application
from server import HRStore


class ServingTests(unittest.TestCase):
    def test_schema_upgrade_preserves_records_but_revokes_legacy_sessions(self):
        import sqlite3
        from server import SCHEMA, password_hash
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'old.db'
            db=sqlite3.connect(path)
            db.executescript(SCHEMA)
            db.execute("INSERT INTO employees(name,email,title,department,location,start_date,role,password) VALUES('Legacy HR','legacy@example.org','HR','People','Remote','2026-10-01','hr',?)",(password_hash('LegacyPassword123!'),))
            db.execute("INSERT INTO sessions VALUES('old-session',1,'old-csrf',9999999999)")
            db.commit();db.close()
            store=HRStore(path)
            db=store.connect()
            try:
                self.assertEqual(db.execute('SELECT name FROM employees').fetchone()[0],'Legacy HR')
                self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],9)
                db.execute('PRAGMA user_version=10');db.commit()
            finally:db.close()
            with self.assertRaises(ValueError):HRStore(path)

    def test_waitress_concurrent_clients_and_stalled_request(self):
        import http.client
        import json
        import socket
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from waitress import create_server
        with tempfile.TemporaryDirectory() as temporary:
            store=HRStore(Path(temporary)/'workspace.db',port=0)
            server=create_server(create_application(store),host='127.0.0.1',port=0,threads=4,channel_timeout=1,cleanup_interval=1,asyncore_loop_timeout=0.1,max_request_body_size=16384)
            port=int(server.effective_port)
            store.server_port=port
            store.allowed_hosts={f'127.0.0.1:{port}'}
            thread=threading.Thread(target=server.run,daemon=True);thread.start()
            stalled=None
            def call(method,path,data=None,cookie='',csrf='',key=''):
                client=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
                headers={'Content-Type':'application/json','Connection':'close','Cookie':cookie,'X-CSRF-Token':csrf,'X-Setup-Token':store.bootstrap_token}
                if key:headers['Idempotency-Key']=key
                try:
                    client.request(method,path,json.dumps(data) if data is not None else None,headers)
                    response=client.getresponse()
                    return response.status,json.loads(response.read()),response.getheader('Set-Cookie','').split(';')[0]
                finally:client.close()
            try:
                setup=call('POST','/api/setup',{'name':'Server HR','email':'hr@example.org','password':'ServerPassword123!','include_samples':False})
                self.assertEqual(setup[0],201)
                first_cookie,first_csrf=setup[2],setup[1]['csrf']
                login=call('POST','/api/login',{'email':'hr@example.org','password':'ServerPassword123!'})
                second_cookie,second_csrf=login[2],login[1]['csrf']
                stalled=socket.create_connection(('127.0.0.1',port),timeout=5)
                stalled.sendall(f'POST /api/login HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: 1000\r\n\r\n{{'.encode())
                body={'title':'One logical operation','due_date':'2026-12-31'}
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures=[pool.submit(call,'POST','/api/goals',body,cookie,csrf,'shared-operation-123456') for cookie,csrf in ((first_cookie,first_csrf),(second_cookie,second_csrf))]
                    results=[future.result(timeout=5) for future in futures]
                self.assertEqual([r[0] for r in results],[201,201])
                self.assertEqual(results[0][1]['id'],results[1][1]['id'])
                state=call('GET','/api/state',cookie=second_cookie)[1]
                self.assertEqual(len(state['goals']),1)
                self.assertGreater(call('GET','/api/changes',cookie=first_cookie)[1]['revision'],0)
            finally:
                if stalled:stalled.close()
                server.task_dispatcher.shutdown()
                server.close()
                thread.join(timeout=3)

    def test_https_origin_and_secure_cookie_through_wsgi(self):
        import json
        with tempfile.TemporaryDirectory() as temporary:
            store=HRStore(Path(temporary)/'workspace.db',public_origin='https://hr.internal',port=8000)
            app=create_application(store)
            def call(path,method='GET',data=None,scheme='https',origin=None):
                raw=json.dumps(data).encode() if data is not None else b''
                environ={'REQUEST_METHOD':method,'PATH_INFO':path,'QUERY_STRING':'','HTTP_HOST':'hr.internal','REMOTE_ADDR':'10.0.0.2','wsgi.url_scheme':scheme,'wsgi.input':io.BytesIO(raw),'CONTENT_LENGTH':str(len(raw)),'CONTENT_TYPE':'application/json','HTTP_X_SETUP_TOKEN':store.bootstrap_token}
                if origin:environ['HTTP_ORIGIN']=origin
                result={}
                def start(status,headers):result.update(status=int(status.split()[0]),headers=dict(headers))
                result['body']=b''.join(app(environ,start))
                return result
            self.assertEqual(call('/api/session',scheme='http')['status'],403)
            self.assertEqual(call('/api/setup','POST',{},origin='https://other.internal')['status'],403)
            setup=call('/api/setup','POST',{'name':'HR','email':'hr@example.org','password':'SupportedPassword123!','include_samples':False},origin='https://hr.internal')
            self.assertEqual(setup['status'],201)
            self.assertIn('; Secure',setup['headers']['Set-Cookie'])
            self.assertEqual(call('/')['status'],200)

