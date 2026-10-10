"""Protected scale/recovery case beyond the previous interactive audit ceiling."""
from contextlib import closing
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from audit_integrity import verify
from backup import create_backup,restore_backup
from server import HRStore


def main():
    if not str(ROOT).startswith('/private/tmp/openpeople-isolated-test-') or os.environ.get('PYTHONDONTWRITEBYTECODE')!='1':raise SystemExit('Use the protected isolation runner.')
    with tempfile.TemporaryDirectory(prefix='openpeople-large-audit-') as folder:
        path=Path(folder);store=HRStore(path/'private/workspace.db',port=0)
        count=200005
        with closing(store.connect()) as db:
            started=time.monotonic()
            with db:db.executemany("INSERT INTO security_events(actor_id,action,address,created_at,details) VALUES(NULL,'Fictional scale event','local','2026-10-09','{}')",(() for _ in range(count)))
            inserted=time.monotonic()-started
            assert not verify(db)['passed']  # Interactive request budget remains bounded.
            started=time.monotonic();anchor=verify(db,maximum=None);elapsed=time.monotonic()-started
            assert anchor['passed'] and anchor['chains']['security_events']['count']==count
        archive=create_backup(store.db_path,path/'archives','Fictional scale recovery passphrase only!')
        recovered=restore_backup(archive,path/'recovered','Fictional scale recovery passphrase only!')
        with closing(__import__('sqlite3').connect(recovered)) as db:
            db.row_factory=__import__('sqlite3').Row
            assert verify(db,anchor,maximum=None)['passed']
        result={'passed':True,'fictional_events':count,'insert_seconds':round(inserted,3),'full_verification_seconds':round(elapsed,3),'streaming_full_verification':True,'interactive_budget_preserved':True,'encrypted_restore_anchor_verified':True,'database_bytes':Path(store.db_path).stat().st_size,'enterprise_load_certification':False}
    result['temporary_folder_removed']=not path.exists();print(json.dumps(result))


if __name__=='__main__':main()
