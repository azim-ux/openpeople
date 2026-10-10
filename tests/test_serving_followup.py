import http.client
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
import unittest

from server import HRStore,SCHEMA
import serving


class ServingFollowup(unittest.TestCase):
    def test_hardened_server_closes_trickle_bodies_and_reserves_capacity(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=HRStore(Path(temporary)/'private/workspace.db',port=0)
            factory=getattr(serving,'create_hardened_server',None)
            self.assertIsNotNone(factory,'Production must use a request-deadline and pending-connection budget.')
            server=factory(store,port=0,request_deadline=0.6,pending_limit=12)
            port=int(server.effective_port);store.allowed_hosts={f'127.0.0.1:{port}'}
            thread=threading.Thread(target=server.run,daemon=True);thread.start();connections=[]
            try:
                for _ in range(100):
                    connection=socket.create_connection(('127.0.0.1',port),timeout=1)
                    try:connection.sendall(f'POST /api/login HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: 1000\r\n\r\n{{'.encode())
                    except OSError:pass
                    connections.append(connection)
                deadline=time.monotonic()+1
                while time.monotonic()<deadline:
                    for connection in connections:
                        try:connection.sendall(b' ')
                        except OSError:pass
                    time.sleep(0.1)
                client=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
                client.request('GET','/api/session',headers={'Connection':'close'})
                response=client.getresponse();response.read();client.close()
                self.assertEqual(response.status,200)
                self.assertLessEqual(sum(not channel.requests and not channel.will_close for channel in server.active_channels.values()),12)
            finally:
                for connection in connections:connection.close()
                server.task_dispatcher.shutdown();server.close();thread.join(timeout=3)

    def test_fresh_fragmented_login_survives_existing_slow_clients(self):
        import json
        with tempfile.TemporaryDirectory() as temporary:
            store=HRStore(Path(temporary)/'private/workspace.db',port=0)
            server=serving.create_hardened_server(store,port=0,request_deadline=5,pending_limit=12,peer_pending_limit=4)
            port=int(server.effective_port);store.allowed_hosts={f'127.0.0.1:{port}'}
            thread=threading.Thread(target=server.run,daemon=True);thread.start();sockets=[]
            try:
                for _ in range(12):
                    channel=socket.create_connection(('127.0.0.1',port),timeout=2)
                    channel.sendall(f'POST /api/policies HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Length: 1000\r\n\r\n{{'.encode());sockets.append(channel)
                time.sleep(.1)
                client=http.client.HTTPConnection('127.0.0.1',port,timeout=2)
                raw=json.dumps({'name':'Fresh HR','email':'fresh@example.org','password':'SyntheticNewPassword123!'}).encode()
                client.putrequest('POST','/api/setup');client.putheader('Content-Type','application/json');client.putheader('Content-Length',str(len(raw)));client.putheader('X-Setup-Token',store.bootstrap_token);client.endheaders()
                time.sleep(.1);client.send(raw)
                response=client.getresponse();response.read();client.close()
                self.assertEqual(response.status,201)
            finally:
                for channel in sockets:channel.close()
                server.task_dispatcher.shutdown();server.close();thread.join(timeout=3)

    def test_legacy_open_sessions_are_preserved_for_correction(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'workspace.db';db=sqlite3.connect(path);db.executescript(SCHEMA)
            db.execute("INSERT INTO employees(name,email,title,department,location,start_date) VALUES('Legacy','legacy@example.org','Analyst','People','Local','2026-01-01')")
            for date in ('2026-10-08','2026-10-09'):
                db.execute('INSERT INTO attendance(employee_id,work_date,check_in) VALUES(1,?,?)',(date,date+'T09:00:00+05:30'))
            db.execute('PRAGMA user_version=2');db.commit();db.close()
            store=HRStore(path)
            db=store.connect()
            try:
                rows=[dict(row) for row in db.execute('SELECT * FROM attendance ORDER BY id')]
                self.assertEqual(len(rows),2)
                self.assertEqual(rows[0]['requires_correction'],1)
                self.assertEqual(rows[1]['requires_correction'],0)
                self.assertTrue(all(row['check_out'] is None for row in rows))
            finally:db.close()
