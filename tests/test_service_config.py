import json
from pathlib import Path
import tempfile
import unittest

from probe_oidc_https import certificates
from service_config import configure_identity,load_environment


class IdentityConfiguration(unittest.TestCase):
    def test_private_validated_no_overwrite_and_no_plaintext_secrets_in_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ca,_=certificates(root)
            account={'email':'person@example.org','username':'Fictional user','userID':'fictional','emailVerified':True,'hash':'$2b$12$'+'A'*53}
            target=root/'service'
            def configure(**changes):
                args={'target':target,'origin':'https://127.0.0.1:8001','issuer':'https://127.0.0.1:5556/dex','certificate':root/'server.pem','key':root/'server.key','ca':ca,'users':[account]};args.update(changes)
                return configure_identity(**args)
            for changes in ({'origin':'http://example.org'},{'issuer':'https://user:pass@example.org/dex'},{'issuer':'https://127.0.0.1/dex/'},{'origin':'https://127.0.0.1/hr'},{'issuer':'https://wrong.example.org/dex'},
                            {'users':[]},{'users':[account,account]},{'users':[{**account,'hash':'plaintext-password'}]},{'users':[{**account,'emailVerified':False}]}):
                with self.subTest(changes=changes),self.assertRaises(ValueError):configure(**changes)
                self.assertFalse(target.exists())
            result=configure();env=json.loads((target/'app-env.json').read_text())
            self.assertEqual(load_environment(target/'app-env.json'),env)
            self.assertNotIn(env['OPENPEOPLE_OIDC_CLIENT_SECRET'],json.dumps(result))
            self.assertEqual(target.stat().st_mode & 0o777,0o700)
            for name in ('dex.json','app-env.json'):self.assertEqual((target/name).stat().st_mode & 0o777,0o600)
            self.assertFalse(result['service_started']);self.assertFalse(result['production_acceptance_passed'])
            with self.assertRaises(ValueError):configure()
            settings=target/'app-env.json';settings.write_text(json.dumps({**env,'PATH':'untrusted'}))
            with self.assertRaises(ValueError):load_environment(settings)
            settings.chmod(0o644)
            with self.assertRaises(ValueError):load_environment(settings)
            (root/'server.key').chmod(0o644)
            with self.assertRaises(ValueError):configure(target=root/'invalid-service')
