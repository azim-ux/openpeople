"""Versioned encrypted SQLite snapshots for user-chosen cloud-synced folders."""
import argparse
import getpass
import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC=b'OPENPEOPLE-BACKUP-1\n'
MAX_BYTES=256*1024*1024


@contextmanager
def process_lock(db_path, purpose, timeout=5):
    """Short config locks and a separate run lock work across CLI/host processes."""
    path=Path(db_path).with_suffix('.backup-'+purpose+'.lock')
    descriptor=os.open(path,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    os.chmod(path,0o600)
    deadline=time.monotonic()+timeout
    with os.fdopen(descriptor,'r+b') as lock:
        if os.name=='nt':
            import msvcrt
            if not path.stat().st_size:lock.write(b'0');lock.flush()
        else:import fcntl
        while True:
            try:
                if os.name=='nt':lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                else:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except (OSError,BlockingIOError) as error:
                if time.monotonic()>=deadline:raise ValueError('A backup operation is already running. Try again shortly.') from error
                time.sleep(0.025)
        try:yield
        finally:
            if os.name=='nt':lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(lock.fileno(),fcntl.LOCK_UN)


def destination_matches(config):
    folder=Path(config['folder']);identity=config.get('destination_identity')
    if not identity or not folder.is_dir():return False
    try:
        status=folder.stat()
        marker=folder/identity['marker']
        return not marker.is_symlink() and marker.read_text()==identity['value'] and status.st_dev==identity['device'] and status.st_ino==identity['inode']
    except (OSError,KeyError):return False


def passphrase_key(passphrase,salt):
    if not isinstance(passphrase,str) or not 16<=len(passphrase)<=1024:
        raise ValueError('Use a backup passphrase of 16–1024 characters.')
    return Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(passphrase.encode())


def atomic_private_write(path,data):
    path=Path(path)
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.openpeople-',delete=False) as output:
        temporary=Path(output.name)
        try:
            os.chmod(temporary,0o600)
            output.write(data);output.flush();os.fsync(output.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def safe_folder(db_path,folder):
    db_path=Path(db_path).resolve()
    folder=Path(folder).expanduser().resolve()
    if db_path.is_relative_to(folder):
        raise ValueError('Keep the live database outside the cloud-synced backup folder.')
    return folder


def create_backup(db_path,folder,passphrase,destination_identity=None,archive_prefix='openpeople'):
    db_path=Path(db_path).resolve()
    if not db_path.is_file() or not db_path.with_suffix('.key').is_file():
        raise ValueError('Workspace database and key must exist.')
    folder=safe_folder(db_path,folder)
    salt,nonce=secrets.token_bytes(16),secrets.token_bytes(12)
    key=passphrase_key(passphrase,salt)
    with tempfile.TemporaryDirectory(prefix='openpeople-backup-') as temporary:
        snapshot=Path(temporary)/'workspace.db'
        with closing(sqlite3.connect(db_path.as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(snapshot)) as destination:
            source.backup(destination)
            os.chmod(snapshot,0o600)
            destination.execute('DELETE FROM sessions')
            destination.execute('DELETE FROM oidc_states')
            destination.execute('DELETE FROM idempotency')
            if destination.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mfa_recovery_codes'").fetchone():
                destination.execute('DELETE FROM mfa_recovery_codes')
            destination.execute('UPDATE employees SET totp_pending=NULL')
            destination.commit()
            if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('The database snapshot failed its integrity check.')
        if snapshot.stat().st_size>MAX_BYTES:
            raise ValueError('This backup format currently supports databases up to 256 MB.')
        bundle=io.BytesIO()
        with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('workspace.db',snapshot.read_bytes())
            archive.writestr('workspace.key',db_path.with_suffix('.key').read_bytes())
            archive.writestr('manifest.json',json.dumps({'format':1,'created_at':datetime.now(timezone.utc).isoformat(),'sessions_removed':True}))
        header=MAGIC+salt+nonce
        encrypted=header+AESGCM(key).encrypt(nonce,bundle.getvalue(),header)
    if destination_identity:
        if not destination_matches({'folder':str(folder),'destination_identity':destination_identity}):
            raise ValueError('The backup destination is missing or changed. Reconfigure it locally.')
    else:folder.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(folder).free<len(encrypted)+1024*1024:
        raise ValueError('There is insufficient free space at the backup destination.')
    timestamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    output=folder/f'{archive_prefix}-{timestamp}-{secrets.token_hex(4)}.opbackup'
    atomic_private_write(output,encrypted)
    if hashlib.sha256(output.read_bytes()).digest()!=hashlib.sha256(encrypted).digest():
        output.unlink(missing_ok=True)
        raise ValueError('The new archive failed its read-back check. Previous backups were retained.')
    return output


def restore_backup(archive_path,destination,passphrase):
    destination=Path(destination).expanduser().resolve()
    if destination.exists():
        raise ValueError('Restore into a new directory; existing workspaces are never overwritten.')
    source=Path(archive_path)
    if source.stat().st_size>MAX_BYTES+1024*1024:
        raise ValueError('The backup is too large for this restore format.')
    raw=source.read_bytes()
    if not raw.startswith(MAGIC) or len(raw)<len(MAGIC)+44:
        raise ValueError('This is not a supported OpenPeople encrypted backup.')
    end=len(MAGIC);salt=raw[end:end+16];nonce=raw[end+16:end+28];header=raw[:end+28]
    try:
        plaintext=AESGCM(passphrase_key(passphrase,salt)).decrypt(nonce,raw[end+28:],header)
    except InvalidTag as error:
        raise ValueError('Wrong passphrase or damaged backup; no workspace was restored.') from error
    try:
        with zipfile.ZipFile(io.BytesIO(plaintext)) as archive:
            if archive.namelist()!=['workspace.db','workspace.key','manifest.json'] or sum(info.file_size for info in archive.infolist())>MAX_BYTES+65536:
                raise ValueError('Invalid backup contents.')
            database=archive.read('workspace.db');vault_key=archive.read('workspace.key')
            if json.loads(archive.read('manifest.json')).get('format')!=1:
                raise ValueError('Unsupported backup manifest.')
            Fernet(vault_key)
        with tempfile.TemporaryDirectory(prefix='openpeople-restore-check-') as temporary:
            check=Path(temporary)/'check.db';check.write_bytes(database)
            with closing(sqlite3.connect(check)) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA user_version').fetchone()[0] not in (2,3,4,5,6,7,8,9):
                    raise ValueError('The backup database failed validation.')
                if db.execute('PRAGMA user_version').fetchone()[0]>=7:
                    from audit_integrity import verify
                    db.row_factory=sqlite3.Row
                    if not verify(db,maximum=None)['passed']:raise ValueError('The backup audit history failed verification; no workspace was restored.')
                for table in ('employees','sessions','oidc_states','app_settings'):
                    db.execute(f'SELECT 1 FROM {table} LIMIT 1')
                db.execute('DELETE FROM sessions');db.execute('DELETE FROM oidc_states');db.execute('DELETE FROM idempotency')
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mfa_recovery_codes'").fetchone():
                    db.execute('DELETE FROM mfa_recovery_codes')
                db.execute('UPDATE employees SET totp_pending=NULL')
                db.commit()
            database=check.read_bytes()
    except (zipfile.BadZipFile,sqlite3.Error,KeyError,TypeError,json.JSONDecodeError) as error:
        raise ValueError('Invalid backup contents; no workspace was restored.') from error
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.mkdir(mode=0o700)  # Exclusive creation also protects concurrent restore attempts.
    try:
        db_path=destination/'workspace.db'
        atomic_private_write(db_path,database)
        atomic_private_write(db_path.with_suffix('.key'),vault_key)
    except BaseException:
        for item in destination.iterdir():
            item.unlink()
        destination.rmdir()
        raise
    return db_path


def configure_backup(db_path,folder,passphrase,interval_minutes=60,retention_count=30):
    db_path=Path(db_path)
    folder=safe_folder(db_path,folder)
    passphrase_key(passphrase,secrets.token_bytes(16))
    if not isinstance(interval_minutes,int) or not 5<=interval_minutes<=10080:
        raise ValueError('Choose a backup interval from 5 minutes to one week.')
    if type(retention_count) is not int or not 2<=retention_count<=1000:
        raise ValueError('Retain between 2 and 1000 backups per configuration generation.')
    vault=Fernet(db_path.with_suffix('.key').read_bytes())
    folder.mkdir(parents=True,exist_ok=True)
    generation=secrets.token_hex(16)
    workspace=hashlib.sha256(db_path.with_suffix('.key').read_bytes()).hexdigest()[:12]
    marker=f'.openpeople-destination-{workspace}'
    marker_value=secrets.token_hex(32)
    with process_lock(db_path,'config'):
        atomic_private_write(folder/marker,marker_value.encode())
        status=folder.stat()
        identity={'marker':marker,'value':marker_value,'device':status.st_dev,'inode':status.st_ino}
        configuration={'generation':generation,'folder':str(folder),'destination_identity':identity,'archive_prefix':f'openpeople-{workspace}-{generation[:8]}','encrypted_passphrase':vault.encrypt(passphrase.encode()).decode(),'interval_minutes':interval_minutes,'retention_count':retention_count,'last_success':None,'last_filename':None,'last_error':None,'last_attempt':None,'destination_available':True,'destination_checked_at':datetime.now(timezone.utc).isoformat()}
        atomic_private_write(db_path.with_suffix('.backup.json'),json.dumps(configuration).encode())


def backup_status(db_path,check_destination=True):
    from cloud_backup import cloud_status
    cloud=cloud_status(db_path)
    path=Path(db_path).with_suffix('.backup.json')
    if not path.is_file():
        return {'configured':False,'provider_upload_verified':False,'cloud':cloud}
    try:
        config=json.loads(path.read_text())
        last=datetime.fromisoformat(config['last_success']).timestamp() if config.get('last_success') else 0
        result={'configured':True,'interval_minutes':config['interval_minutes'],'retention_count':config.get('retention_count'),'last_success':config.get('last_success'),'last_filename':config.get('last_filename'),'last_error':config.get('last_error'),'last_attempt':config.get('last_attempt'),'provider_upload_verified':False,'destination_available':destination_matches(config) if check_destination else config.get('destination_available',False),'destination_checked_at':config.get('destination_checked_at'),'overdue':not last or time.time()-last>config['interval_minutes']*120,'destination_verification_required':not bool(config.get('destination_identity'))}
        job=Path(db_path).with_suffix('.backup-job.json')
        if job.is_file():result['job']={key:value for key,value in json.loads(job.read_text()).items() if key!='host_instance'}
        result['cloud']=cloud
        return result
    except (ValueError,KeyError,OSError):
        return {'configured':False,'configuration_error':True,'provider_upload_verified':False,'cloud':cloud}


def refresh_destination_health(db_path):
    path=Path(db_path).with_suffix('.backup.json')
    if not path.is_file():return
    with process_lock(db_path,'config'):config=json.loads(path.read_text())
    available=destination_matches(config)
    with process_lock(db_path,'config'):
        latest=json.loads(path.read_text())
        if latest.get('generation')==config.get('generation'):
            latest.update(destination_available=available,destination_checked_at=datetime.now(timezone.utc).isoformat())
            atomic_private_write(path,json.dumps(latest).encode())


def run_configured_backup(db_path):
    db_path=Path(db_path)
    with process_lock(db_path,'run',timeout=0):
        path=db_path.with_suffix('.backup.json')
        with process_lock(db_path,'config'):
            if not path.is_file():raise ValueError('Configure backups with the local backup command first.')
            config=json.loads(path.read_text())
        error=None;output=None
        try:
            if not destination_matches(config):raise ValueError('The backup destination is missing or changed. Reconfigure it locally.')
            passphrase=Fernet(db_path.with_suffix('.key').read_bytes()).decrypt(config['encrypted_passphrase'].encode()).decode()
            output=create_backup(db_path,config['folder'],passphrase,destination_identity=config['destination_identity'],archive_prefix=config['archive_prefix'])
            archives=sorted(Path(config['folder']).glob(config['archive_prefix']+'-*.opbackup'),key=lambda item:item.stat().st_mtime_ns,reverse=True)
            for old in archives[config['retention_count']:]:
                if old!=output and not old.is_symlink():old.unlink()
        except Exception as caught:
            error=caught
        available=destination_matches(config)
        with process_lock(db_path,'config'):
            latest=json.loads(path.read_text())
            # A newer generation belongs to the operator, not the old run.
            if latest.get('generation')==config.get('generation'):
                latest.update(destination_available=available,destination_checked_at=datetime.now(timezone.utc).isoformat(),last_attempt=datetime.now(timezone.utc).isoformat(),last_error=('Backup failed. Check destination identity, available storage and local configuration.' if error else None))
                if output and not error:latest.update(last_success=datetime.now(timezone.utc).isoformat(),last_filename=output.name)
                atomic_private_write(path,json.dumps(latest).encode())
        if error:raise error
    # Provider I/O must happen outside database, local run and config locks.
    from cloud_backup import sync_after_backup
    sync_after_backup(db_path,output)
    return output


def recover_interrupted_job(db_path,instance_id):
    path=Path(db_path).with_suffix('.backup-job.json')
    if not path.is_file():return
    with process_lock(db_path,'job'):
        job=json.loads(path.read_text())
        if job.get('status') in ('Queued','Running') and job.get('host_instance')!=instance_id:
            job.update(status='Failed',error='Backup interrupted by host shutdown. Retry after checking the destination.',finished_at=datetime.now(timezone.utc).isoformat())
            atomic_private_write(path,json.dumps(job).encode())


def prepare_backup_job(server,actor_id):
    """Prepare a queued response; start work only after the HTTP transaction commits."""
    status=backup_status(server.db_path,check_destination=False)
    if not status.get('configured') or not status.get('destination_available'):
        raise ValueError('Configure and verify an available backup destination first.')
    with server.backup_job_lock:
        path=Path(server.db_path).with_suffix('.backup-job.json')
        previous=json.loads(path.read_text()) if path.exists() else {}
        if previous.get('status') in ('Queued','Running') and previous.get('host_instance')==server.instance_id:
            raise ValueError('A backup is already queued or running.')
        job={'id':secrets.token_hex(16),'status':'Queued','requested_by':actor_id,'created_at':datetime.now(timezone.utc).isoformat(),'host_instance':server.instance_id}
        atomic_private_write(path,json.dumps(job).encode())
    def work():
        job['status']='Running';atomic_private_write(path,json.dumps(job).encode())
        try:
            result=run_configured_backup(server.db_path)
            job.update(status='Completed',filename=result.name)
        except Exception:
            job.update(status='Failed',error='Backup failed. Check destination and local configuration.')
        job['finished_at']=datetime.now(timezone.utc).isoformat()
        atomic_private_write(path,json.dumps(job).encode())
        from workspace import security_event
        with closing(server.connect()) as db:
            with db:security_event(db,'Backup completed' if job['status']=='Completed' else 'Backup failed',actor_id,'local',{'job_id':job['id'],'status':job['status']})
    thread=threading.Thread(target=work,name='requested-backup',daemon=True)
    with server.backup_job_lock:
        server.backup_threads=[item for item in server.backup_threads if item.is_alive()]
        server.backup_threads.append(thread)
    def cancelled():
        job.update(status='Failed',error='Backup request was not committed. Please retry.')
        atomic_private_write(path,json.dumps(job).encode())
    server_pending=thread.start
    return {key:value for key,value in job.items() if key!='host_instance'},server_pending,cancelled


def verify_backup(archive_path,passphrase):
    with tempfile.TemporaryDirectory(prefix='openpeople-recovery-drill-') as temporary:
        restored=restore_backup(archive_path,Path(temporary)/'restored',passphrase)
        with closing(sqlite3.connect(restored)) as db:
            vault=Fernet(restored.with_suffix('.key').read_bytes())
            for row in db.execute('SELECT totp_secret FROM employees WHERE totp_secret IS NOT NULL'):
                vault.decrypt(row[0].encode())
            counts={table:db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('employees','sessions','audit','security_events')}
        return {'verified':True,'archive_sha256':hashlib.sha256(Path(archive_path).read_bytes()).hexdigest(),'restored_counts':counts,'provider_upload_verified':False}


def start_backup_worker(db_path,store=None):
    stop=threading.Event()
    def worker():
        while not stop.is_set():
            try:
                refresh_destination_health(db_path)
                status=backup_status(db_path,check_destination=False)
                last=datetime.fromisoformat(status['last_success']).timestamp() if status.get('last_success') else 0
                if status.get('configured') and time.time()-last>=status['interval_minutes']*60:
                    archive=run_configured_backup(db_path)
                    if store:
                        from workspace import security_event
                        with closing(store.connect()) as db:
                            with db:security_event(db,'Automatic backup completed',None,'local',{'filename':archive.name})
            except Exception:
                if store:
                    from workspace import security_event
                    with closing(store.connect()) as db:
                        with db:security_event(db,'Automatic backup failed',None,'local',{'status':'Failed'})
                # No paths, passphrases, or personnel data in failure output.
                print('Automatic backup failed. Check the local configuration and available storage.',flush=True)
            stop.wait(30)
    thread=threading.Thread(target=worker,name='encrypted-backup',daemon=True);thread.start()
    return stop,thread


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Encrypted OpenPeople backups. Never cloud-sync the live SQLite database.')
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('configure','create','run','status'):
        child=sub.add_parser(command);child.add_argument('--db',type=Path,default=Path(__file__).parent/'data'/'openpeople.db')
        if command in ('configure','create'):
            child.add_argument('--folder',type=Path,required=True)
        if command=='configure':
            child.add_argument('--interval',type=int,default=60)
            child.add_argument('--retain',type=int,default=30)
    child=sub.add_parser('restore');child.add_argument('archive',type=Path);child.add_argument('--destination',type=Path,required=True)
    child=sub.add_parser('verify');child.add_argument('archive',type=Path)
    args=parser.parse_args()
    try:
        if args.command=='status':
            print(json.dumps(backup_status(args.db),indent=2))
        elif args.command=='run':
            print(run_configured_backup(args.db))
        else:
            passphrase=getpass.getpass('Backup passphrase (at least 16 characters): ')
            if args.command in ('create','configure') and passphrase!=getpass.getpass('Confirm passphrase: '):
                raise ValueError('Passphrases do not match.')
            if args.command=='configure':
                configure_backup(args.db,args.folder,passphrase,args.interval,args.retain)
                print('Backup folder configured. Keep the passphrase separately for recovery on another computer.')
            elif args.command=='create':
                print(create_backup(args.db,args.folder,passphrase))
            elif args.command=='verify':
                print(json.dumps(verify_backup(args.archive,passphrase),indent=2))
            else:
                print(restore_backup(args.archive,args.destination,passphrase))
    except (ValueError,OSError) as error:
        parser.exit(1,str(error)+'\n')
