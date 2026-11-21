"""Token-protected private subscription with locally measured, calibrated traffic.

Uses only Python's standard library. Provider web sessions never reach this service.
"""
import argparse
import base64
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import ssl
import tempfile
import threading
import time
from urllib.parse import urlsplit


def atomic_json(path, value):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.state-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def counters(interface):
    base = Path('/sys/class/net') / interface / 'statistics'
    return (Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            int((base / 'rx_bytes').read_text()), int((base / 'tx_bytes').read_text()))


class Traffic:
    def __init__(self, billing_path, state_path, interface, counter_reader=counters,
                 provider_usage_path=None):
        self.billing_path, self.state_path = Path(billing_path), Path(state_path)
        self.interface, self.counter_reader = interface, counter_reader
        self.provider_usage_path = Path(provider_usage_path) if provider_usage_path else None
        self.lock = threading.Lock()

    def sample(self):
        with self.lock:
            billing = json.loads(self.billing_path.read_text(encoding='utf-8'))
            assert billing['quota_bytes'] > 0 and billing['used_bytes'] >= 0
            now = datetime.now(timezone.utc)
            if self.provider_usage_path:
                try:
                    provider = json.loads(self.provider_usage_path.read_text(encoding='utf-8'))
                    used = provider['used_bytes']
                    sampled = datetime.fromisoformat(provider['sampled_at'])
                    expire = provider.get('expire', billing['expire'])
                    if type(used) is int and used >= 0 and type(expire) is int and expire > 0:
                        age = now - sampled
                        return {'upload': 0, 'download': used, 'total': billing['quota_bytes'],
                                'expire': expire, 'calibrated_at': sampled.isoformat(),
                                'mode': 'provider-api' if age < timedelta(minutes=30) else 'provider-api-stale'}
                except (OSError, ValueError, TypeError, KeyError):
                    pass
            cycle = billing['cycle_start'] + '/' + billing['cycle_end']
            generation = billing['calibration_id']
            boot, rx, tx = self.counter_reader(self.interface)
            try:
                state = json.loads(self.state_path.read_text(encoding='utf-8'))
            except FileNotFoundError:
                state = None
            today = now.astimezone(timezone(timedelta(hours=8))).date().isoformat()
            valid_cycle = billing['cycle_start'] <= today < billing['cycle_end']
            if state is None or state.get('calibration_id') != generation:
                # Each new provider calibration starts a fresh delta from current counters.
                state = {'calibration_id': generation, 'cycle': cycle,
                         'used_bytes': billing['used_bytes'], 'boot': boot, 'rx': rx, 'tx': tx}
            else:
                if state['boot'] != boot:
                    # New boot starts counters at zero; include traffic since that boot.
                    delta = rx + tx
                else:
                    # Counter resets must never subtract previously measured usage.
                    delta = max(rx - state['rx'], 0) + max(tx - state['tx'], 0)
                state['used_bytes'] += delta
                state.update(boot=boot, rx=rx, tx=tx)
            state['sampled_at'] = now.isoformat()
            atomic_json(self.state_path, state)
            return {'upload': 0, 'download': state['used_bytes'], 'total': billing['quota_bytes'],
                    'expire': billing['expire'], 'valid_cycle': valid_cycle,
                    'calibrated_at': billing['calibrated_at'],
                    'mode': 'estimate' if valid_cycle else 'needs-calibration'}


class LimitedServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16
    def __init__(self, *args, tls_context=None, **kwargs):
        self.capacity = threading.BoundedSemaphore(16)
        self.tls_context = tls_context
        super().__init__(*args, **kwargs)

    def get_request(self):
        sock, addr = super().get_request()
        sock.settimeout(5)
        if self.tls_context:
            sock = self.tls_context.wrap_socket(sock, server_side=True, do_handshake_on_connect=False)
        return sock, addr

    def process_request(self, request, client_address):
        if not self.capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.capacity.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.capacity.release()

    def handle_error(self, request, client_address):
        # Never log paths, tokens, body data or client IPs.
        print('request-failed', flush=True)


def subscription_handler(config, traffic):
    token = Path(config['token_file']).read_text(encoding='ascii').strip()
    assert re.fullmatch(r'[a-f0-9]{64}', token)
    target = ('/sub/' + token).encode('ascii')

    class Handler(BaseHTTPRequestHandler):
        server_version = 'PrivateSubscription'
        sys_version = ''
        def log_message(self, *_):
            pass

        def do_HEAD(self):
            self.respond(False)

        def do_GET(self):
            self.respond(True)

        def respond(self, send_body):
            if len(self.path) > 4096 or not hmac.compare_digest(self.path.encode('utf-8'), target):
                self.send_error(404, 'Not Found')
                return
            try:
                stats = traffic.sample()
                data = Path(config['yaml_file']).read_bytes()
                if not data or len(data) > 2_000_000:
                    raise ValueError('Invalid private configuration')
                self.send_response(200)
                self.send_header('Content-Type', 'text/yaml; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'private, no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('profile-update-interval', '12')
                title = '个人VPS（东京主备·流量同步）' if stats['mode'].startswith('provider-api') else '个人VPS（东京主备·流量估算）'
                self.send_header('profile-title', 'base64:' + base64.b64encode(title.encode('utf-8')).decode('ascii'))
                self.send_header('Content-Disposition', 'attachment; filename="PersonalVPS-Tokyo-Estimated.yaml"')
                # Keep the cumulative estimate visible until a fresh calibration is available.
                self.send_header('Subscription-Userinfo', '; '.join(
                    f'{key}={stats[key]}' for key in ['upload', 'download', 'total', 'expire']))
                self.send_header('X-Traffic-Mode', stats['mode'])
                self.send_header('X-Traffic-Calibrated-At', stats['calibrated_at'])
                self.end_headers()
                if send_body:
                    self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                # Do not include exception details or private paths in the response.
                self.send_error(503, 'Temporarily Unavailable')
    return Handler


def acme_handler(webroot):
    folder = Path(webroot) / '.well-known/acme-challenge'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            m = re.fullmatch(r'/\.well-known/acme-challenge/([A-Za-z0-9_-]{20,256})', self.path)
            if not m:
                self.send_error(404, 'Not Found')
                return
            path = folder / m.group(1)
            if path.is_symlink() or not path.is_file():
                self.send_error(404, 'Not Found')
                return
            body = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(body)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    traffic = Traffic(config['billing_file'], config['state_file'], config['interface'],
                      provider_usage_path=config.get('provider_usage_file'))
    servers = []
    if config.get('acme_port'):
        servers.append(LimitedServer((config['listen'], config['acme_port']), acme_handler(config['webroot'])))
    cert, key = Path(config['certificate_file']), Path(config['key_file'])
    if cert.is_file() and key.is_file():
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.minimum_version = ssl.TLSVersion.TLSv1_2
        tls.load_cert_chain(cert, key)
        servers.append(LimitedServer((config['listen'], config['https_port']), subscription_handler(config, traffic), tls_context=tls))
    if not servers:
        raise RuntimeError('No listener configured')
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print('private-subscription-ready', flush=True)
    while True:
        try:
            traffic.sample()
        except Exception:
            print('traffic-sample-failed', flush=True)
        time.sleep(30)


if __name__ == '__main__':
    main()
