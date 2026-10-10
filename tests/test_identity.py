import base64
import json
import os
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from test_app import HRFlows
from identity import totp


class IdentityFlows(HRFlows):
    def test_authenticator_attempts_are_rate_limited(self):
        self.setup_admin()
        secret=self.request('POST','/api/mfa/begin',{})[1]['secret']
        for _ in range(9):
            self.assertEqual(self.request('POST','/api/mfa/confirm',{'otp':'invalid'})[0],400)
        self.assertEqual(self.request('POST','/api/mfa/confirm',{'otp':totp(secret)})[0],429)

    def test_enforced_mfa_blocks_data_until_enrollment(self):
        self.setup_admin()
        self.add_employee()
        self.assertEqual(self.request('POST','/api/policies',{'require_mfa':True})[0],400)
        secret=self.request('POST','/api/mfa/begin',{})[1]['secret']
        self.assertEqual(self.request('POST','/api/mfa/confirm',{'otp':totp(secret)})[0],200)
        self.assertEqual(self.request('POST','/api/policies',{'require_mfa':True})[0],200)
        self.login('person@example.org','EmployeePass123!')
        self.assertTrue(self.request('GET','/api/session')[1]['mfa_setup_required'])
        self.assertEqual(self.request('GET','/api/state')[0],403)
        self.assertEqual(self.request('POST','/api/goals',{'title':'Cannot bypass','due_date':'2026-12-31'})[0],403)
        employee_secret=self.request('POST','/api/mfa/begin',{})[1]['secret']
        self.assertEqual(self.request('POST','/api/mfa/confirm',{'otp':totp(employee_secret)})[0],200)
        self.assertEqual(self.request('GET','/api/state')[0],200)

    def test_totp_rfc_vector_and_enrollment_login(self):
        secret = base64.b32encode(b'12345678901234567890').decode()
        self.assertEqual(totp(secret, 59),'287082')
        self.setup_admin()
        enrollment = self.request('POST','/api/mfa/begin',{})
        self.assertEqual(enrollment[0],200)
        secret = enrollment[1]['secret']
        self.assertEqual(self.request('POST','/api/mfa/confirm',{'otp':'١٢٣٤٥٦'})[0],400)
        self.assertEqual(self.request('POST','/api/mfa/confirm',{'otp':'000000'})[0],400)
        code = totp(secret)
        self.assertEqual(self.request('POST','/api/mfa/confirm',{'otp':code})[0],200)
        self.request('POST','/api/logout',{})
        self.assertEqual(self.request('POST','/api/login',{'email':'admin@example.org','password':'TestPassword123!'})[0],401)
        self.assertEqual(self.request('POST','/api/login',{'email':'admin@example.org','password':'TestPassword123!','otp':code})[0],401)
        self.assertEqual(self.request('POST','/api/login',{'email':'admin@example.org','password':'TestPassword123!','otp':totp(secret,time.time()+30)})[0],200)
        self.assertTrue(self.request('GET','/api/security')[1]['mfa_enabled'])

    def test_idle_timeout_and_password_change_revocation(self):
        self.setup_admin()
        old_cookie = self.cookie
        self.assertEqual(self.request('POST','/api/password',{'current_password':'bad','new_password':'NewPassword123!'})[0],403)
        status,result = self.request('POST','/api/password',{'current_password':'TestPassword123!','new_password':'NewPassword123!'})
        self.assertEqual(status,200)
        self.csrf = result['csrf']
        new_cookie = self.cookie
        self.cookie = old_cookie
        self.assertEqual(self.request('GET','/api/state')[0],401)
        self.cookie = new_cookie
        db=self.server.connect()
        with db:
            db.execute('UPDATE sessions SET last_seen=?',(time.time()-1801,))
        db.close()
        self.assertEqual(self.request('GET','/api/state')[0],401)

    def test_oidc_pkce_signature_nonce_and_provisioned_identity(self):
        self.setup_admin()
        self.request('POST','/api/logout',{})
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk.update(kid='test-key',alg='RS256',use='sig')
        metadata={'issuer':'https://idp.example','authorization_endpoint':'https://idp.example/auth','token_endpoint':'https://idp.example/token','jwks_uri':'https://idp.example/keys'}
        def response(data):
            obj=type('Response',(),{'raise_for_status':lambda self:None,'json':lambda self:data})()
            return obj
        with patch.dict(os.environ,{'OPENPEOPLE_OIDC_ISSUER':'https://idp.example','OPENPEOPLE_OIDC_CLIENT_ID':'openpeople'}), patch('identity.requests.get',side_effect=lambda url,**kw:response({'keys':[jwk]} if url.endswith('/keys') else metadata)):
            started=self.request('GET','/api/sso/start')
            self.assertEqual(started[0],200)
            params=parse_qs(urlsplit(started[1]['url']).query)
            self.assertEqual(params['code_challenge_method'],['S256'])
            state=params['state'][0]
            claims={'iss':'https://idp.example','aud':'openpeople','sub':'employee-subject','email':'admin@example.org','email_verified':True,'nonce':params['nonce'][0],'iat':int(time.time()),'exp':int(time.time())+60}
            token=jwt.encode(claims,key,algorithm='RS256',headers={'kid':'test-key'})
            with patch('identity.requests.post',return_value=response({'id_token':token})) as exchange:
                result=self.request('GET',f'/api/sso/callback?state={state}&code=test-code')
                self.assertEqual(result[0],303,result)
                self.assertIn('code_verifier',exchange.call_args.kwargs['data'])
                self.assertEqual(self.request('GET','/api/state')[0],200)
                sso_cookie='openpeople_sso='+state
                self.assertEqual(self.request('GET',f'/api/sso/callback?state={state}&code=test-code',extra={'Cookie':sso_cookie})[0],401)
            self.request('POST','/api/logout',{})
            started=self.request('GET','/api/sso/start')
            params=parse_qs(urlsplit(started[1]['url']).query)
            claims['nonce']='incorrect-nonce'
            token=jwt.encode(claims,key,algorithm='RS256',headers={'kid':'test-key'})
            with patch('identity.requests.post',return_value=response({'id_token':token})):
                self.assertEqual(self.request('GET',f'/api/sso/callback?state={params["state"][0]}&code=bad-code')[0],401)
            for scenario in ('signature','unprovisioned','unverified','audience','expired'):
                started=self.request('GET','/api/sso/start')
                params=parse_qs(urlsplit(started[1]['url']).query)
                invalid={**claims,'nonce':params['nonce'][0]}
                signing_key=key
                if scenario=='signature':signing_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
                if scenario=='unprovisioned':invalid.update(email='unknown@example.org',sub='unknown-subject')
                if scenario=='unverified':invalid['email_verified']=False
                if scenario=='audience':invalid['aud']='other-client'
                if scenario=='expired':invalid.update(iat=int(time.time())-300,exp=int(time.time())-200)
                token=jwt.encode(invalid,signing_key,algorithm='RS256',headers={'kid':'test-key'})
                with patch('identity.requests.post',return_value=response({'id_token':token})):
                    status=self.request('GET',f'/api/sso/callback?state={params["state"][0]}&code=invalid-code')[0]
                    self.assertEqual(status,403 if scenario=='unprovisioned' else 401,scenario)
                self.assertEqual(self.request('GET','/api/state')[0],401)
            self.login()
            factor_secret=self.request('POST','/api/mfa/begin',{})[1]['secret']
            self.assertEqual(self.request('POST','/api/mfa/confirm',{'otp':totp(factor_secret)})[0],200)
            self.request('POST','/api/logout',{})
            started=self.request('GET','/api/sso/start')
            params=parse_qs(urlsplit(started[1]['url']).query)
            valid={**claims,'nonce':params['nonce'][0]}
            token=jwt.encode(valid,key,algorithm='RS256',headers={'kid':'test-key'})
            with patch('identity.requests.post',return_value=response({'id_token':token})):
                self.assertEqual(self.request('GET',f'/api/sso/callback?state={params["state"][0]}&code=factor-code')[0],303)
            self.csrf=self.request('GET','/api/session')[1]['csrf']
            self.assertTrue(self.request('GET','/api/session')[1]['mfa_verify_required'])
            self.assertEqual(self.request('GET','/api/state')[0],403)
            self.assertEqual(self.request('POST','/api/mfa/verify',{'otp':'invalid'})[0],401)
            self.assertEqual(self.request('POST','/api/mfa/verify',{'otp':totp(factor_secret,time.time()+30)})[0],200)
            self.assertEqual(self.request('GET','/api/state')[0],200)


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(IdentityFlows(name) for name in IdentityFlows.__dict__ if name.startswith('test_'))
