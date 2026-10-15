"""Local Douyin acceptance with real media and mocked downloads; no live requests."""
import contextlib
from datetime import datetime
import hashlib
import http.cookiejar
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SKILL = ROOT / 'skill-package/social-video-download'
if not SKILL.is_dir():
    SKILL = ROOT.parent  # Public repository: social-video-download/tests/.
sys.path.insert(0, str(SKILL / 'scripts'))
import download as dl
import yt_dlp

class Response(io.BytesIO):
    def __init__(self, data, content_type='video/mp4', length=None):
        super().__init__(data)
        self.headers = {'Content-Type': content_type, 'Content-Length': str(len(data) if length is None else length)}

class DownloadAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix='acceptance-')
        cls.base = Path(cls.temp.name)
        cls.fixture = cls.base / 'fixture.mp4'
        subprocess.run([str(dl.FFMPEG), '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'testsrc2=size=640x360:rate=25', '-f', 'lavfi', '-i', 'sine=frequency=440',
                        '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac',
                        '-pix_fmt', 'yuv420p', str(cls.fixture)], check=True, capture_output=True, timeout=60)
        cls.plain = cls.fixture.read_bytes()
        cls.video_only = cls.base / 'video-only.mp4'
        cls.audio_only = cls.base / 'audio-only.m4a'
        for mapping, target in (('0:v:0', cls.video_only), ('0:a:0', cls.audio_only)):
            subprocess.run([str(dl.FFMPEG), '-v', 'error', '-i', str(cls.fixture), '-map', mapping,
                            '-c', 'copy', str(target)], check=True, capture_output=True, timeout=60)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.output = self.base / self._testMethodName
        self.output.mkdir()
        self.args = type('Args', (), {'media_url': None, 'local_media': None,
                                    'cookies_file': None, 'ffprobe': dl.FFPROBE,
                                    'title': None, 'video_id': None})()
        self.url = 'https://v.douyin.com/local-test/'
        self.profile = {'id': 'fixture-id', 'title': 'title/special:*', 'author': 'fixture'}

    def download_fixture(self, url, stage, *args):
        target = stage / 'video.mp4'
        shutil.copyfile(self.fixture, target)
        return target, self.profile

    def save(self):
        with patch.object(dl, 'douyin_download', side_effect=self.download_fixture):
            return dl.save_one(self.url, self.output, self.args)

    def test_save_and_duplicate_keep_original_bytes(self):
        result = self.save()
        saved = Path(result['path'])
        self.assertEqual(saved.read_bytes(), self.plain)
        self.assertTrue(saved.name.startswith('抖音_'))
        record = json.loads(saved.with_suffix('.source.json').read_text(encoding='utf-8'))
        self.assertEqual(record['platform'], 'douyin')
        self.assertNotIn('media_url', record)
        with patch.object(dl, 'douyin_download', side_effect=AssertionError('must reuse existing')):
            reused = dl.save_one(self.url, self.output, self.args)
        self.assertEqual(reused['status'], 'already_exists')
        self.assertEqual(reused['path'], result['path'])

    def test_existing_file_not_overwritten(self):
        name = dl.safe_name('抖音_' + self.profile['title']) + '_[fixture-id].mp4'
        original = self.output / name
        original.write_bytes(b'user-original')
        result = self.save()
        self.assertEqual(original.read_bytes(), b'user-original')
        self.assertNotEqual(Path(result['path']), original)

    def test_error_page_rejected_without_residue(self):
        self.args.media_url = 'https://media.example/fixture?token=private'
        with patch.object(dl.urllib.request, 'urlopen', return_value=Response(b'<html>login</html>', 'text/html')):
            with self.assertRaises(dl.DownloadError) as caught:
                dl.save_one(self.url, self.output, self.args)
        self.assertEqual(caught.exception.code, 'not_media')
        self.assertEqual(list(self.output.iterdir()), [])

    def test_incomplete_response_rejected(self):
        self.args.media_url = 'https://media.example/fixture'
        with patch.object(dl.urllib.request, 'urlopen', return_value=Response(self.plain, length=len(self.plain)+1)):
            with self.assertRaises(dl.DownloadError) as caught:
                dl.save_one(self.url, self.output, self.args)
        self.assertEqual(caught.exception.code, 'incomplete_download')
        self.assertEqual(list(self.output.iterdir()), [])

    def test_short_reads_keep_complete_video(self):
        class ShortResponse(Response):
            def read(self, size=-1):
                return super().read(min(size, 4093) if size >= 0 else size)
        self.args.media_url = 'https://media.example/fixture?token=private'
        with patch.object(dl.urllib.request, 'urlopen', return_value=ShortResponse(self.plain)):
            result = dl.save_one(self.url, self.output, self.args)
        self.assertEqual(Path(result['path']).read_bytes(), self.plain)
        self.assertNotIn('private', Path(result['path']).with_suffix('.source.json').read_text(encoding='utf-8'))

    def test_non_video_rejected_without_residue(self):
        self.args.local_media = self.base / 'invalid.mp4'
        self.args.local_media.write_bytes(b'not-a-video' * 1000)
        with self.assertRaises(dl.DownloadError):
            dl.save_one(self.url, self.output, self.args)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_scope_batch_and_modal_normalization(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            status = dl.main(['--dry-run', 'https://example.org/x https://v.douyin.com/test/ https://www.douyin.com/user/test'])
        results = json.loads(output.getvalue())['results']
        self.assertEqual(status, 1)
        self.assertEqual([r['status'] for r in results], ['failed', 'planned', 'failed'])
        links = dl.extract_links('https://www.douyin.com/?modal_id=123 https://www.douyin.com/?modal_id=123')
        self.assertEqual(links, ['https://www.douyin.com/video/123'])
        evil = 'https://fake-douyin.com/?modal_id=123'
        self.assertEqual(dl.extract_links(evil), [evil])
        with patch.object(dl, 'douyin_download', side_effect=AssertionError('must not request')):
            with self.assertRaises(dl.DownloadError):
                dl.save_one(evil, self.output, self.args)

    def test_cookies_are_scoped_to_douyin(self):
        cookies = self.base / 'cookies.txt'
        cookies.write_text('# Netscape HTTP Cookie File\n'
                           '.douyin.com\tTRUE\t/\tTRUE\t2147483647\tsession\tneeded\n'
                           '.unrelated.example\tTRUE\t/\tTRUE\t2147483647\tsecret\tunused\n', encoding='utf-8')
        class FakeYDL:
            def __init__(self, options):
                self.cookiejar = http.cookiejar.CookieJar()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract_info(self, url, download):
                observed.extend((c.name, c.value) for c in self.cookiejar)
                return {'id': 'fixture-id', 'title': 'fixture'}
            def prepare_filename(self, info):
                return str(self_fixture)
            def process_ie_result(self, info, download):
                return info
        stage = self.base
        self_fixture = self.fixture
        observed = []
        with patch.object(yt_dlp, 'YoutubeDL', FakeYDL):
            dl.douyin_download(self.url, stage, cookies)
        self.assertEqual(observed, [('session', 'needed')])

    def test_different_direct_links_reuse_legacy_record(self):
        self.profile['id'] = '123'
        result = self.save()
        sidecar = Path(result['path']).with_suffix('.source.json')
        record = json.loads(sidecar.read_text(encoding='utf-8'))
        record.pop('video_id')  # Compatibility with the previously installed version.
        sidecar.write_text(json.dumps(record), encoding='utf-8')
        with patch.object(dl, 'douyin_download', side_effect=AssertionError('no network needed')):
            reused = dl.save_one('https://www.douyin.com/share/video/123?tracking=other', self.output, self.args)
        self.assertEqual(reused['path'], result['path'])
        self.assertEqual(reused['status'], 'already_exists')

    def test_short_links_resolve_id_before_download_and_scan_once(self):
        observed = []
        fixture = self.fixture
        class FakeYDL:
            def __init__(self, options):
                self.path = Path(options['outtmpl'].replace('%(ext)s', 'mp4'))
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract_info(self, url, download):
                observed.append(('metadata', download))
                return {'id': '123', 'title': 'same-video'}
            def process_ie_result(self, info, download):
                observed.append(('media', download))
                shutil.copyfile(fixture, self.path)
                return info
            def prepare_filename(self, info):
                return str(self.path)
        with patch.object(yt_dlp, 'YoutubeDL', FakeYDL), patch.object(dl, 'SourceIndex', wraps=dl.SourceIndex) as scans:
            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                status = dl.main(['--output', str(self.output),
                                  'https://v.douyin.com/one/ https://v.douyin.com/two/'])
        results = json.loads(stdout.getvalue())['results']
        self.assertEqual(status, 0)
        self.assertEqual(scans.call_count, 1)
        self.assertEqual(observed, [('metadata', False), ('media', True), ('metadata', False)])
        self.assertEqual([r['status'] for r in results], ['downloaded', 'already_exists'])
        self.assertEqual(results[0]['path'], results[1]['path'])
        record = json.loads(next(self.output.glob('*.source.json')).read_text(encoding='utf-8'))
        self.assertEqual(record['video_id'], '123')

    def test_corrupt_existing_media_is_not_reused(self):
        original = Path(self.save()['path'])
        original.write_bytes(b'broken-video')
        replacement = self.save()
        self.assertEqual(replacement['status'], 'downloaded')
        self.assertNotEqual(original, Path(replacement['path']))
        self.assertEqual(original.read_bytes(), b'broken-video')

    def test_fallback_id_mismatch_rejected_before_copy(self):
        self.args.local_media = self.fixture
        self.args.video_id = '456'
        with self.assertRaises(dl.DownloadError) as caught:
            dl.save_one('https://www.douyin.com/video/123', self.output, self.args)
        self.assertEqual(caught.exception.code, 'video_id_mismatch')
        self.assertEqual(list(self.output.iterdir()), [])

    def test_malformed_and_outside_records_are_ignored(self):
        (self.output/'bad.source.json').write_text('[]', encoding='utf-8')
        record = {'request_id': dl.fingerprint(self.url), 'platform': 'douyin', 'file': '../fixture.mp4'}
        (self.output/'outside.source.json').write_text(json.dumps(record), encoding='utf-8')
        self.assertEqual(self.save()['status'], 'downloaded')

    def test_extractor_errors_do_not_claim_login_without_evidence(self):
        cases = [('Fresh cookies (not necessarily logged in) are needed', 'douyin_extractor_unavailable'),
                 ('HTTP Error 403: Forbidden', 'access_denied'),
                 ('HTTP Error 429: Too Many Requests', 'rate_limited'),
                 ('verification challenge captcha', 'verification_required'),
                 ('login required', 'login_required'), ('getaddrinfo failed', 'network_error')]
        for message, code in cases:
            class FakeYDL:
                def __init__(self, options):
                    pass
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def extract_info(self, url, download):
                    raise RuntimeError(message + ' https://private.invalid/?token=secret')
            with self.subTest(code=code), patch.object(yt_dlp, 'YoutubeDL', FakeYDL):
                with self.assertRaises(dl.DownloadError) as caught:
                    dl.douyin_download(self.url, self.base)
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn('secret', str(caught.exception))

    def test_expected_audio_rejects_video_only(self):
        self.args.local_media = self.video_only
        self.args.require_audio = True
        with self.assertRaises(dl.DownloadError) as caught:
            dl.save_one(self.url, self.output, self.args)
        self.assertEqual(caught.exception.code, 'missing_audio')
        self.assertEqual(list(self.output.iterdir()), [])

    def test_expected_duration_rejects_preview(self):
        self.args.local_media = self.fixture
        self.args.expected_duration = 145.0
        with self.assertRaises(dl.DownloadError) as caught:
            dl.save_one(self.url, self.output, self.args)
        self.assertEqual(caught.exception.code, 'duration_mismatch')
        self.assertEqual(list(self.output.iterdir()), [])

    def make_manifest(self):
        manifest = self.output / 'browser.json'
        manifest.write_text(json.dumps({'assets': [], 'failures': [
            {'name': 'media-video-avc1', 'url': 'https://test.douyinvod.com/video?token=private'},
            {'name': 'media-audio-und-mp4a', 'url': 'https://test.douyinvod.com/audio?token=private'}]}), encoding='utf-8')
        self.args.browser_manifest = manifest
        self.args.expected_duration = 2.0
        return manifest

    def test_browser_pair_muxes_original_codecs_and_reuses_identity(self):
        self.make_manifest()
        def transfer(url, target, **kwargs):
            shutil.copyfile(self.video_only if '/video?' in url else self.audio_only, target)
        with patch('browser_manifest.media_download', side_effect=transfer) as transfers:
            result = dl.save_one('https://www.douyin.com/video/123', self.output, self.args)
        self.assertEqual(transfers.call_count, 2)
        self.assertEqual(result['codec'], 'h264')
        self.assertEqual(result['audio_codecs'], ['aac'])
        sidecar = Path(result['path']).with_suffix('.source.json').read_text(encoding='utf-8')
        self.assertNotIn('private', sidecar)
        self.assertEqual(json.loads(sidecar)['source_url'], 'https://www.douyin.com/video/123')
        with patch('browser_manifest.media_download', side_effect=AssertionError('must reuse')):
            reused = dl.save_one('https://www.douyin.com/share/video/123', self.output, self.args)
        self.assertEqual(reused['status'], 'already_exists')

    def test_browser_pair_rejects_ambiguous_or_untrusted_sources(self):
        manifest = self.make_manifest()
        for replacement in ('https://unrelated.example/audio', 'https://test.douyinvod.com/video?token=private'):
            data = json.loads(manifest.read_text(encoding='utf-8'))
            data['failures'][1]['url'] = replacement
            manifest.write_text(json.dumps(data), encoding='utf-8')
            with patch('browser_manifest.media_download', side_effect=AssertionError('no transfer')):
                with self.assertRaises(dl.DownloadError) as caught:
                    dl.save_one('https://www.douyin.com/video/123', self.output, self.args)
            self.assertEqual(caught.exception.code, 'invalid_browser_manifest')

    def test_browser_pair_rejects_wrong_duration_before_promotion(self):
        self.make_manifest()
        self.args.expected_duration = 145.0
        with patch('browser_manifest.media_download', side_effect=lambda url, target, **kw: shutil.copyfile(self.video_only, target)):
            with self.assertRaises(dl.DownloadError) as caught:
                dl.save_one('https://www.douyin.com/video/123', self.output, self.args)
        self.assertEqual(caught.exception.code, 'duration_mismatch')
        self.assertFalse(list(self.output.glob('*.mp4')))

    def test_existing_video_only_is_not_reused_when_audio_expected(self):
        original = Path(self.save()['path'])
        shutil.copyfile(self.video_only, original)
        self.args.require_audio = True
        result = self.save()
        self.assertEqual(result['status'], 'downloaded')
        self.assertNotEqual(Path(result['path']), original)
        self.assertEqual(result['audio_streams'], 1)

if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DownloadAcceptance))
    report = {'verified_at': datetime.now().astimezone().isoformat(), 'platform': 'douyin', 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'passed': result.wasSuccessful(),
              'scope': '真实本地视频含音轨生成/采样解码 + 模拟下载；本轮未新增平台请求',
              'skill_files_sha256': {p.relative_to(SKILL).as_posix():
                  hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in SKILL.rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts}}
    (ROOT / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
