"""HTTPS OIDC protocol acceptance against a separate, synthetic local provider.

Uses real discovery, authorization redirects, PKCE code exchange and JWKS HTTP
requests. This is not certification of a commercial provider or a live tenant.
Run only under scripts/test_isolated.py's enforced disposable sandbox.
"""
import base64
import datetime
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import secrets
import ssl
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from identity import totp
from server import HRStore
from serving import create_hardened_server

PASSWORD = 'FictionalIdentityPassword123!'
CLIENT = 'fictional-openpeople-client'
CLIENT_SECRET = 'fictional-provider-secret'


def certificates(folder):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Disposable test CA')])
    now = datetime.datetime.now(datetime.timezone.utc)
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
          .public_key(key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), True)
          .sign(key, hashes.SHA256()))
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1')]))
            .issuer_name(name).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key()), False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .sign(key, hashes.SHA256()))
    ca_path, cert_path, key_path = (folder / name for name in ('ca.pem', 'server.pem', 'server.key'))
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    key_path.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    return ca_path, context


def main():
    if not str(ROOT).startswith('/private/tmp/openpeople-isolated-test-') or os.environ.get('PYTHONDONTWRITEBYTECODE') != '1':
        raise SystemExit('Use the enforced isolation runner for the identity probe.')
    with tempfile.TemporaryDirectory(prefix='openpeople-https-identity-') as folder:
        temporary = Path(folder)
        ca, context = certificates(temporary)
        codes, counts, mode = {}, {'discovery': 0, 'pkce_verified': 0, 'jwks': 0}, {'name': 'valid'}
        signing = {'key': rsa.generate_private_key(public_exponent=65537, key_size=2048), 'kid': 'initial-key'}

        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send_json(self, status, value):
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                parsed = urlsplit(self.path)
                if parsed.path == '/idp/.well-known/openid-configuration':
                    counts['discovery'] += 1
                    self.send_json(200, {'issuer': issuer, 'authorization_endpoint': issuer + '/authorize', 'token_endpoint': issuer + '/token', 'jwks_uri': issuer + '/keys'})
                elif parsed.path == '/idp/keys':
                    counts['jwks'] += 1
                    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing['key'].public_key()))
                    self.send_json(200, {'keys': [{**jwk, 'kid': signing['kid'], 'alg': 'RS256', 'use': 'sig'}]})
                elif parsed.path == '/idp/authorize':
                    params = parse_qs(parsed.query)
                    assert params['client_id'] == [CLIENT] and params['redirect_uri'] == [origin + '/api/sso/callback']
                    assert params['response_type'] == ['code'] and params['code_challenge_method'] == ['S256']
                    code = secrets.token_urlsafe(24)
                    codes[code] = (params, mode['name'])
                    self.send_response(303)
                    self.send_header('Location', params['redirect_uri'][0] + '?' + urlencode({'state': params['state'][0], 'code': code}))
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                else:
                    self.send_json(404, {})

            def do_POST(self):
                if self.path != '/idp/token':
                    return self.send_json(404, {})
                basic = 'Basic ' + base64.b64encode((CLIENT + ':' + CLIENT_SECRET).encode()).decode()
                assert self.headers.get('Authorization') == basic
                params = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
                pending = codes.pop(params.get('code', [''])[0], None)
                if not pending:
                    return self.send_json(400, {'error': 'invalid_grant'})
                original, scenario = pending
                challenge = base64.urlsafe_b64encode(hashlib.sha256(params['code_verifier'][0].encode()).digest()).decode().rstrip('=')
                assert original['code_challenge'] == [challenge]
                assert params['redirect_uri'] == original['redirect_uri'] and params['grant_type'] == ['authorization_code']
                counts['pkce_verified'] += 1
                claims = {'iss': issuer, 'aud': CLIENT, 'sub': 'fictional-employee-subject', 'email': 'person@example.org', 'email_verified': True, 'nonce': original['nonce'][0], 'iat': int(time.time()), 'exp': int(time.time()) + 120}
                key = signing['key']
                if scenario == 'nonce':
                    claims['nonce'] = 'wrong-nonce'
                elif scenario == 'audience':
                    claims['aud'] = 'another-client'
                elif scenario == 'expired':
                    claims.update(iat=int(time.time()) - 300, exp=int(time.time()) - 200)
                elif scenario == 'unverified':
                    claims['email_verified'] = False
                elif scenario == 'unprovisioned':
                    claims.update(sub='unprovisioned-subject', email='missing@example.org')
                elif scenario == 'signature':
                    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                self.send_json(200, {'id_token': jwt.encode(claims, key, algorithm='RS256', headers={'kid': signing['kid']}), 'token_type': 'Bearer'})

        class Bridge(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.forward()

            def do_POST(self):
                self.forward()

            def do_PATCH(self):
                self.forward()

            def forward(self):
                upstream = http.client.HTTPConnection('127.0.0.1', backend.effective_port, timeout=10)
                try:
                    headers = {key: value for key, value in self.headers.items() if key.lower() not in ('connection', 'x-forwarded-proto', 'x-forwarded-for')}
                    headers.update({'Connection': 'close', 'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '127.0.0.1'})
                    upstream.request(self.command, self.path, self.rfile.read(int(self.headers.get('Content-Length', '0'))), headers)
                    response = upstream.getresponse()
                    body = response.read()
                    self.send_response(response.status)
                    for key, value in response.getheaders():
                        if key.lower() not in ('connection', 'server', 'date', 'content-length'):
                            self.send_header(key, value)
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                finally:
                    upstream.close()

        provider = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
        bridge = ThreadingHTTPServer(('127.0.0.1', 0), Bridge)
        provider.socket = context.wrap_socket(provider.socket, server_side=True)
        bridge.socket = context.wrap_socket(bridge.socket, server_side=True)
        issuer, origin = f'https://127.0.0.1:{provider.server_port}/idp', f'https://127.0.0.1:{bridge.server_port}'
        store = HRStore(temporary / 'private/workspace.db', public_origin=origin, port=0)
        backend = create_hardened_server(store, port=0)
        workers = [threading.Thread(target=target, daemon=True) for target in (provider.serve_forever, bridge.serve_forever, backend.run)]
        previous = {key: os.environ.get(key) for key in ('OPENPEOPLE_OIDC_ISSUER', 'OPENPEOPLE_OIDC_CLIENT_ID', 'OPENPEOPLE_OIDC_CLIENT_SECRET', 'REQUESTS_CA_BUNDLE', 'NO_PROXY')}
        os.environ.update({'OPENPEOPLE_OIDC_ISSUER': issuer, 'OPENPEOPLE_OIDC_CLIENT_ID': CLIENT, 'OPENPEOPLE_OIDC_CLIENT_SECRET': CLIENT_SECRET, 'REQUESTS_CA_BUNDLE': str(ca), 'NO_PROXY': '127.0.0.1,localhost'})
        for worker in workers:
            worker.start()
        def session():
            client = requests.Session()
            client.trust_env = False
            return client
        def call(client, path, method='GET', data=None, csrf=None):
            return client.request(method, origin + path, json=data, headers={'Origin': origin, **({'X-Setup-Token': store.bootstrap_token} if path == '/api/setup' else {}), **({'X-CSRF-Token': csrf} if csrf else {})}, verify=str(ca), timeout=12, allow_redirects=False)
        checks = {}
        try:
            admin = session()
            response = call(admin, '/api/setup', 'POST', {'setup_token': store.bootstrap_token, 'name': 'Fictional HR', 'email': 'hr@example.org', 'password': PASSWORD})
            assert response.status_code == 201, response.text
            csrf = response.json()['csrf']
            response = call(admin, '/api/employees', 'POST', {'name': 'Fictional identity employee', 'email': 'person@example.org', 'title': 'Test only', 'department': 'Test', 'location': 'Remote', 'annual_salary': 600000, 'start_date': '2026-10-01', 'role': 'employee', 'password': PASSWORD}, csrf)
            assert response.status_code == 201, response.text
            employee = response.json()['id']
            def signin(scenario='valid', client=None):
                mode['name'] = scenario
                client = client or session()
                started = call(client, '/api/sso/start')
                assert started.status_code == 200, started.text
                authorize = client.get(started.json()['url'], verify=str(ca), timeout=5, allow_redirects=False)
                assert authorize.status_code == 303
                callback = authorize.headers['Location']
                response = client.get(callback, verify=str(ca), timeout=12, allow_redirects=False)
                return client, response, callback
            client, response, callback = signin()
            assert response.status_code == 303 and call(client, '/api/state').status_code == 200, response.text
            checks['real_https_discovery_pkce_jwks_login'] = True
            assert 'Secure' in response.headers['Set-Cookie'] and 'HttpOnly' in response.headers['Set-Cookie']
            checks['secure_session_cookie'] = True
            assert client.get(callback, verify=str(ca), timeout=10, allow_redirects=False).status_code == 401
            checks['authorization_state_replay_rejected'] = True
            mode['name'] = 'valid'
            bound = session()
            started = call(bound, '/api/sso/start')
            redirect = bound.get(started.json()['url'], verify=str(ca), timeout=5, allow_redirects=False).headers['Location']
            assert session().get(redirect, verify=str(ca), timeout=10, allow_redirects=False).status_code == 401
            assert bound.get(redirect, verify=str(ca), timeout=12, allow_redirects=False).status_code == 303
            checks['state_bound_to_initiating_browser'] = True
            for scenario in ('nonce', 'audience', 'expired', 'unverified', 'unprovisioned', 'signature'):
                candidate, invalid, _ = signin(scenario)
                assert invalid.status_code == (403 if scenario == 'unprovisioned' else 401), (scenario, invalid.status_code)
                assert call(candidate, '/api/state').status_code == 401
                checks[scenario + '_rejected'] = True
            signing.update(key=rsa.generate_private_key(public_exponent=65537, key_size=2048), kid='rotated-key')
            client, response, _ = signin()
            assert response.status_code == 303
            checks['provider_signing_key_rotation'] = True
            user_csrf = call(client, '/api/session').json()['csrf']
            factor = call(client, '/api/mfa/begin', 'POST', {}, user_csrf).json()['secret']
            assert call(client, '/api/mfa/confirm', 'POST', {'otp': totp(factor)}, user_csrf).status_code == 200
            gated, response, _ = signin()
            assert response.status_code == 303 and call(gated, '/api/state').status_code == 403
            gated_session = call(gated, '/api/session').json()
            assert gated_session['mfa_verify_required']
            assert call(gated, '/api/mfa/verify', 'POST', {'otp': totp(factor, time.time() + 30)}, gated_session['csrf']).status_code == 200
            assert call(gated, '/api/state').status_code == 200
            checks['sso_requires_enrolled_local_factor'] = True
            response = call(admin, f'/api/employees/{employee}', 'PATCH', {'status': 'Inactive', 'expected_version': 1}, csrf)
            assert response.status_code == 200, response.text
            inactive, response, _ = signin()
            assert response.status_code == 403 and call(inactive, '/api/state').status_code == 401
            assert call(gated, '/api/state').status_code == 401
            checks['deactivated_identity_and_existing_session_rejected'] = True
            print(json.dumps({'passed': True, 'checks': checks, 'network_calls': counts, 'provider': 'Separate synthetic HTTPS OIDC server on loopback', 'external_tenant_tested': False, 'system_certificate_store_modified': False, 'fictional_data_only': True}))
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            backend.task_dispatcher.shutdown()
            backend.close()
            for service in (bridge, provider):
                service.shutdown()
                service.server_close()
            for worker in workers:
                worker.join(timeout=3)


if __name__ == '__main__':
    main()
