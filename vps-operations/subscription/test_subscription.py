"""Local checks for credential protection, byte accounting, restart and cycle boundary."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from subscription_server import Traffic, LimitedServer, atomic_json, subscription_handler, acme_handler


def beijing_today():
    return datetime.now(timezone(timedelta(hours=8))).date()


class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        today = beijing_today()
        self.billing = {'quota_bytes': 800000, 'used_bytes': 160000, 'expire': 1793404800,
                        'cycle_start': (today - timedelta(days=1)).isoformat(), 'cycle_end': (today + timedelta(days=1)).isoformat(),
                        'calibration_id': 'initial', 'calibrated_at': '2026-10-08T12:00:00Z'}
        self.current = ('boot-1', 100, 200)
        atomic_json(self.root / 'billing.json', self.billing)
        self.traffic = Traffic(self.root / 'billing.json', self.root / 'state.json', 'eth0', lambda _: self.current)

    def tearDown(self):
        self.temp.cleanup()

    def test_bidirectional_delta_and_process_restart(self):
        self.assertEqual(self.traffic.sample()['download'], 160000)
        self.current = ('boot-1', 300, 500)
        self.assertEqual(self.traffic.sample()['download'], 160500)
        restarted = Traffic(self.root / 'billing.json', self.root / 'state.json', 'eth0', lambda _: self.current)
        self.assertEqual(restarted.sample()['download'], 160500)

    def test_reboot_and_counter_reset_do_not_subtract(self):
        self.traffic.sample()
        self.current = ('boot-2', 30, 70)
        self.assertEqual(self.traffic.sample()['download'], 160100)
        self.current = ('boot-2', 1, 2)
        self.assertEqual(self.traffic.sample()['download'], 160100)

    def test_provider_recalibration_replaces_estimate(self):
        self.traffic.sample()
        self.billing.update(calibration_id='new', used_bytes=170000)
        atomic_json(self.root / 'billing.json', self.billing)
        self.current = ('boot-1', 400, 500)
        self.assertEqual(self.traffic.sample()['download'], 170000)

    def test_provider_snapshot_replaces_estimate_even_when_cycle_ends(self):
        snapshot = self.root / 'usage.json'
        traffic = Traffic(self.root / 'billing.json', self.root / 'state.json', 'eth0',
                          lambda _: self.current, provider_usage_path=snapshot)
        self.billing['cycle_end'] = beijing_today().isoformat()
        atomic_json(self.root / 'billing.json', self.billing)
        self.assertEqual(traffic.sample()['mode'], 'needs-calibration')
        now = datetime.now(timezone.utc)
        atomic_json(snapshot, {'used_bytes': 900, 'sampled_at': now.isoformat()})
        self.assertEqual(traffic.sample()['download'], 900)
        self.assertEqual(traffic.sample()['mode'], 'provider-api')
        atomic_json(snapshot, {'used_bytes': 0, 'sampled_at': (now - timedelta(hours=1)).isoformat(),
                               'expire': 1797206400})
        result = traffic.sample()
        self.assertEqual((result['download'], result['total'], result['expire'], result['mode']),
                         (0, 800000, 1797206400, 'provider-api-stale'))

    def test_http_authentication_headers_and_cycle_boundary(self):
        token = 'a' * 64
        (self.root / 'token').write_text(token)
        payload = b'proxies: []\nrules: [MATCH,DIRECT]\n'
        (self.root / 'private.yaml').write_bytes(payload)
        config = {'token_file': str(self.root / 'token'), 'yaml_file': str(self.root / 'private.yaml')}
        server = LimitedServer(('127.0.0.1', 0), subscription_handler(config, self.traffic))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for path in ['/', '/private.yaml', '/sub/wrong', '/sub/' + token + '?foo=bar']:
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    opener.open(base + path)
                self.assertEqual(cm.exception.code, 404)
            with opener.open(base + '/sub/' + token) as response:
                self.assertEqual(response.read(), payload)
                self.assertIn('download=160000', response.headers['Subscription-Userinfo'])
                self.assertEqual(response.headers['X-Traffic-Mode'], 'estimate')
                self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
            self.billing['cycle_end'] = beijing_today().isoformat()
            atomic_json(self.root / 'billing.json', self.billing)
            self.current = ('boot-1', 120, 230)
            with opener.open(base + '/sub/' + token) as response:
                self.assertEqual(response.headers['Subscription-Userinfo'],
                                 'upload=0; download=160050; total=800000; expire=1793404800')
                self.assertEqual(response.headers['X-Traffic-Mode'], 'needs-calibration')
                self.assertEqual(response.read(), payload)
        finally:
            server.shutdown()
            server.server_close()

    def test_port80_only_serves_challenge(self):
        folder = self.root / '.well-known/acme-challenge'
        folder.mkdir(parents=True)
        name = 'x' * 43
        (folder / name).write_text('challenge-proof')
        server = LimitedServer(('127.0.0.1', 0), acme_handler(self.root))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with opener.open(base + '/.well-known/acme-challenge/' + name) as response:
                self.assertEqual(response.read(), b'challenge-proof')
            for path in ['/', '/sub/' + 'a'*64, '/.well-known/acme-challenge/../../private.yaml']:
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    opener.open(base + path)
                self.assertEqual(cm.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
