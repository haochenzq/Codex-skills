"""Refresh V.PS authorization and publish usage for the Tokyo subscription."""

from datetime import date, datetime, timezone
from http.client import HTTPSConnection
import json
import os
from pathlib import Path
import sys
import tempfile
import time


AUTH = Path('/var/lib/personal-vps-api/auth.json')
SNAPSHOT = Path('/var/lib/personal-vps-api-usage/usage.json')
CONFIG = Path('/etc/personal-vps-api.json')


def write_json(path, value, mode):
    stream = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         delete=False)
    pending = Path(stream.name)
    try:
        with stream:
            json.dump(value, stream)
            stream.flush()
            pending.chmod(mode)
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def api(path, *, bearer=None, data=None):
    headers = {'Accept': 'application/json'}
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    if data is not None:
        headers['Content-Type'] = 'application/json'
    connection = HTTPSConnection('vps.hosting', timeout=15)
    try:
        connection.request('GET' if data is None else 'POST', path,
                           None if data is None else json.dumps(data), headers)
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f'{path}: HTTP {response.status}')
        result = json.loads(response.read(262145))
        if not isinstance(result, dict) or result.get('error'):
            raise RuntimeError(f'{path}: V.PS rejected the request')
        return result
    finally:
        connection.close()


def access_token(auth):
    if auth.get('token') and auth.get('expires_at', 0) > time.time() + 120:
        return auth['token']
    response = api('/api/token', data={'refresh_token': auth['refresh_token']})
    result = response.get('data', response)
    token = result['token']
    if not isinstance(token, str) or not token:
        raise ValueError('invalid access token response')
    refresh = result.get('refresh') or result.get('refresh_token') or auth['refresh_token']
    write_json(AUTH, {'token': token, 'expires_at': int(result.get('expires_at') or 0),
                      'refresh_token': refresh}, 0o600)
    return token


def byte_count(value):
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    raise ValueError('invalid V.PS bandwidth counter')


def sync():
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    service_id = int(config['service_id'])
    vm_id = int(config['vm_id'])
    if service_id <= 0 or vm_id <= 0:
        raise ValueError('invalid V.PS service or VM ID')
    service = f'/api/service/{service_id}'
    vm = f'{service}/vms/{vm_id}'
    auth = json.loads(AUTH.read_text(encoding='utf-8'))
    token = access_token(auth)
    try:
        bandwidth = api(vm, bearer=token)['vm']['bandwidth']
    except RuntimeError as error:
        if not str(error).endswith('HTTP 401'):
            raise
        auth = json.loads(AUTH.read_text(encoding='utf-8'))
        auth.pop('token', None)
        token = access_token(auth)
        bandwidth = api(vm, bearer=token)['vm']['bandwidth']

    used = byte_count(bandwidth['data_received']) + byte_count(bandwidth['data_sent'])
    now = datetime.now(timezone.utc)
    snapshot = {'used_bytes': used, 'sampled_at': now.isoformat()}
    try:
        details = api(service, bearer=token)['service']
        due = date.fromisoformat(details['next_due'])
        snapshot['expire'] = int(datetime(due.year, due.month, due.day,
                                          tzinfo=timezone.utc).timestamp())
    except (RuntimeError, ValueError, TypeError, KeyError, OSError):
        try:
            previous = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
            if type(previous.get('expire')) is int and previous['expire'] > 0:
                snapshot['expire'] = previous['expire']
        except (FileNotFoundError, ValueError):
            pass
    write_json(SNAPSHOT, snapshot, 0o640)
    print('V.PS usage updated')


if __name__ == '__main__':
    try:
        sync()
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as error:
        message = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(f'V.PS usage sync failed: {message}', file=sys.stderr)
        sys.exit(1)
