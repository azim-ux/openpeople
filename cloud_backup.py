"""Provider-neutral HTTPS WebDAV transport for encrypted snapshots only.

The local operator supplies a dedicated collection and credentials through the
server environment. Upload verifies a fresh remote read-back; this is distinct
from restoration on another physical computer. No HR HTTP caller chooses URLs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import requests

from backup import MAGIC, MAX_BYTES, atomic_private_write, process_lock

TRANSFER_LIMIT = MAX_BYTES + 1024 * 1024
TRANSFER_SECONDS = 60
WORKER_TIMEOUT = 75


def destination_id():
    # Binds cached read-back to the destination/account, not the password.
    value=[os.environ.get(key,'') for key in ('OPENPEOPLE_WEBDAV_URL','OPENPEOPLE_WEBDAV_USER','OPENPEOPLE_WEBDAV_CA')]
    return hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()


def configuration():
    url = os.environ.get('OPENPEOPLE_WEBDAV_URL', '')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or len(url) > 2000:
        raise ValueError('Configure a dedicated HTTPS WebDAV collection without URL credentials, query or fragment.')
    user = os.environ.get('OPENPEOPLE_WEBDAV_USER', '')
    password = os.environ.get('OPENPEOPLE_WEBDAV_PASSWORD', '')
    if not user or not password:
        raise ValueError('Configure WebDAV credentials privately in the server environment.')
    ca = os.environ.get('OPENPEOPLE_WEBDAV_CA')
    return url.rstrip('/') + '/', (user, password), ca or True


def name_checked(name):
    if not isinstance(name, str) or not re.fullmatch(r'openpeople[-A-Za-z0-9_]{1,180}\.opbackup', name):
        raise ValueError('Choose an OpenPeople encrypted snapshot filename without directory components.')
    return name


def digest_file(path):
    if Path(path).is_symlink():
        raise ValueError('Choose an ordinary encrypted snapshot file.')
    with Path(path).open('rb') as file:
        if file.read(len(MAGIC)) != MAGIC or not len(MAGIC) + 64 <= os.fstat(file.fileno()).st_size <= TRANSFER_LIMIT:
            raise ValueError('Only bounded encrypted OpenPeople snapshots can be transferred.')
        file.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: file.read(262144), b''):
            digest.update(chunk)
    return digest.hexdigest()


def remote_read(client, url, auth, ca, output=None, deadline=None):
    deadline = deadline or time.monotonic() + TRANSFER_SECONDS
    digest, size, prefix = hashlib.sha256(), 0, b''
    with client.get(url, auth=auth, verify=ca, timeout=(5, 10), allow_redirects=False, stream=True) as response:
        if response.status_code != 200:
            raise ValueError('The remote snapshot could not be retrieved without redirection.')
        for chunk in response.iter_content(4096):
            size += len(chunk)
            if size > TRANSFER_LIMIT or time.monotonic() > deadline:
                raise ValueError('The remote snapshot exceeds the supported size or time budget.')
            if len(prefix) < len(MAGIC):
                prefix += chunk[:len(MAGIC) - len(prefix)]
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
    if prefix != MAGIC or size < len(MAGIC) + 64:
        raise ValueError('The remote file is not a bounded encrypted OpenPeople snapshot.')
    return digest.hexdigest(), size


def upload_verified(archive):
    archive = Path(archive)
    name = name_checked(archive.name)
    expected = digest_file(archive)
    base, auth, ca = configuration()
    client = requests.Session()
    client.trust_env = False
    try:
        url = base + quote(name, safe='')
        deadline = time.monotonic() + TRANSFER_SECONDS
        with archive.open('rb') as body:
            class BoundedReader:
                def __len__(self):
                    return os.fstat(body.fileno()).st_size

                def read(self, amount=-1):
                    if time.monotonic() > deadline:
                        raise ValueError('The upload exceeded its time budget.')
                    return body.read(amount)
            with client.put(url, data=BoundedReader(), headers={'Content-Type': 'application/octet-stream', 'If-None-Match': '*'}, auth=auth, verify=ca, timeout=(5, 10), allow_redirects=False) as response:
                if response.status_code not in (201, 204, 412):
                    raise ValueError('The cloud upload did not complete without redirection.')
        # A conflicting name is an idempotent retry only if its bytes agree.
        actual, size = remote_read(client, url, auth, ca, deadline=deadline)
        if actual != expected:
            raise ValueError('Remote read-back differs from the local encrypted snapshot; it was not overwritten.')
        return {'filename': name, 'sha256': expected, 'bytes': size, 'uploaded_and_read_back': True, 'off_device_restore_verified': False}
    finally:
        client.close()


def download_verified(name, destination, expected_sha256):
    name_checked(name)
    if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise ValueError('Supply the separately recorded SHA-256 before downloading a recovery snapshot.')
    destination = Path(destination)
    if not destination.is_dir() or destination.is_symlink():
        raise ValueError('Choose an existing dedicated download directory.')
    final = destination / name
    if final.exists() or final.is_symlink():
        raise ValueError('The download destination already contains that filename; no file will be overwritten.')
    base, auth, ca = configuration()
    client = requests.Session()
    client.trust_env = False
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.openpeople-download-', dir=destination, delete=False) as output:
            temporary = Path(output.name)
            digest, _ = remote_read(client, base + quote(name, safe=''), auth, ca, output)
            output.flush()
            os.fsync(output.fileno())
        if digest != expected_sha256:
            raise ValueError('The downloaded snapshot does not match the separately recorded SHA-256.')
        # Atomic, non-overwriting publication; never replace a raced-in file.
        os.link(temporary, final)
        return final
    finally:
        client.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def sync_after_backup(db_path, archive):
    """Called after local backup/config locks are released; failure stays separate."""
    if not os.environ.get('OPENPEOPLE_WEBDAV_URL'):
        return None
    path = Path(db_path).with_suffix('.cloud-status.json')
    try:
        with process_lock(db_path, 'cloud', timeout=0):
            return _sync_locked(path, archive)
    except (OSError, ValueError):
        # An existing transfer owns its status. Never fail a successful local
        # snapshot or overwrite that worker's status when this lock is busy.
        return {'status': 'Skipped', 'error': 'Cloud transfer busy or status storage unavailable; local backup retained.'}


def _sync_locked(path, archive):
    status = {'status': 'Running', 'filename': Path(archive).name, 'started_at': datetime.now(timezone.utc).isoformat(),'destination_id':destination_id()}
    atomic_private_write(path, json.dumps(status).encode())
    try:
        # requests' idle timeout alone cannot stop a server that continuously
        # dribbles bytes. A killable child gives scheduled transfers an absolute
        # deadline and holds no database/local-snapshot lock.
        worker=subprocess.run([sys.executable,str(Path(__file__).resolve()),'upload',str(archive)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=WORKER_TIMEOUT,check=True)
        status.update(json.loads(worker.stdout), status='Verified remote copy')
    except (OSError, ValueError, requests.RequestException, subprocess.SubprocessError):
        status.update(status='Failed', error='Cloud transfer or verification failed. Check the private provider configuration and retained local backup.')
    status['finished_at'] = datetime.now(timezone.utc).isoformat()
    atomic_private_write(path, json.dumps(status).encode())
    return status


def cloud_status(db_path):
    path = Path(db_path).with_suffix('.cloud-status.json')
    result = {'configured': bool(os.environ.get('OPENPEOPLE_WEBDAV_URL')), 'off_device_restore_verified': False}
    if path.is_file():
        try:
            stored=json.loads(path.read_text())
            if not isinstance(stored,dict):raise ValueError('Invalid status')
            if stored.get('destination_id')==destination_id():
                result.update({key:value for key,value in stored.items() if key!='destination_id'})
            else:
                result.update(status='Not verified for current destination',uploaded_and_read_back=False)
        except (ValueError, OSError):
            result.update(status='Unknown', error='Cloud status is unreadable; verify the provider copy separately.')
    result['off_device_restore_verified'] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    upload = sub.add_parser('upload')
    upload.add_argument('archive', type=Path)
    download = sub.add_parser('download')
    download.add_argument('filename')
    download.add_argument('--destination', required=True, type=Path)
    download.add_argument('--sha256', required=True)
    args = parser.parse_args()
    try:
        result = upload_verified(args.archive) if args.command == 'upload' else {'downloaded': str(download_verified(args.filename, args.destination, args.sha256)), 'off_device_restore_verified': False}
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, requests.RequestException):
        parser.exit(1, 'Cloud operation failed; check the dedicated destination, credentials, certificate trust and snapshot hash. No recovery approval was granted.\n')


if __name__ == '__main__':
    main()
