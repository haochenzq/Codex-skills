"""Download user-supplied Douyin video share links to a local video pool."""
from __future__ import annotations

import argparse
import errno
import hashlib
from itertools import chain
import http.cookiejar
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

SKILL_ROOT = Path(__file__).resolve().parents[1]
VENDOR = SKILL_ROOT / 'runtime/python-packages'
if VENDOR.is_dir():
    sys.path.insert(0, str(VENDOR))
DEFAULT_OUTPUT = Path.cwd()
FFMPEG = SKILL_ROOT / 'runtime/ffmpeg/ffmpeg.exe'
FFPROBE = FFMPEG.with_name('ffprobe.exe')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
URL_RE = re.compile(r'https?://[^\s<>\"\u3000]+', re.I)
TRAILING = '.,;!，。；！）)]}》”’'

from download_errors import DownloadError
from media_downloader import media_download
from browser_manifest import duration_tolerance, import_stream_pair

def desktop_roots():
    """Include redirected Windows desktops, without changing browser settings."""
    roots = [Path.home() / 'Desktop', Path.home() / '桌面']
    if os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                roots.append(Path(os.path.expandvars(winreg.QueryValueEx(key, 'Desktop')[0])))
        except OSError:
            pass
    return [p.resolve() for p in roots]


def check_temporary_path(path):
    resolved = Path(path).resolve()
    if any(resolved.is_relative_to(root) for root in desktop_roots()):
        raise DownloadError('desktop_staging_forbidden', '桌面不能用于下载暂存、分享输入或签名清单；请使用系统临时目录或 --temp-dir 指定的项目任务暂存目录。')
    return resolved


def temporary_parent(args):
    parent = check_temporary_path(getattr(args, 'temp_dir', None) or tempfile.gettempdir())
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def promote_exclusive(path, destination):
    """Keep exclusive admission when system temp and library are on different drives."""
    try:
        os.link(path, destination)
    except OSError as exc:
        if exc.errno != errno.EXDEV and getattr(exc, 'winerror', None) != 17:
            raise
        with destination.open('xb') as output:
            try:
                with path.open('rb') as source:
                    shutil.copyfileobj(source, output)
            except BaseException:
                output.close()
                destination.unlink()
                raise

def platform(url):
    try:
        p = urllib.parse.urlsplit(url)
        host = (p.hostname or '').lower()
        valid = p.scheme in ('http', 'https') and not p.username and not p.password and p.port in (None, 80, 443)
    except ValueError:
        valid = False
    if not valid:
        raise DownloadError('invalid_link', '链接必须是正常的 HTTP/HTTPS 抖音分享地址。')
    if host == 'v.douyin.com' and re.fullmatch(r'/[A-Za-z0-9_-]+/?', p.path):
        return 'douyin'
    if (host == 'douyin.com' or host.endswith('.douyin.com')) and re.fullmatch(r'/(?:share/)?video/[0-9]+/?', p.path):
        return 'douyin'
    raise DownloadError('unsupported_link', '仅处理单条抖音视频分享链接，不下载主页、账号或合集。')


def extract_links(text):
    links = []
    for raw in URL_RE.findall(text):
        url = raw.rstrip(TRAILING)
        # Common copied Douyin modal links are normalized to the actual video.
        p = urllib.parse.urlsplit(url)
        q = urllib.parse.parse_qs(p.query)
        host = (p.hostname or '').lower()
        if (host == 'douyin.com' or host.endswith('.douyin.com')) and q.get('modal_id', [''])[0].isdigit():
            url = 'https://www.douyin.com/video/' + q['modal_id'][0]
        if url not in links:
            links.append(url)
    return links

def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()[:16]

def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value))
    return (value.strip(' .')[:65].rstrip(' .') or '未命名视频')

def probe(path, executable=FFPROBE, expected_duration=None, require_audio=False):
    if not Path(executable).is_file():
        raise DownloadError('missing_ffprobe', 'ffprobe 不存在；请检查技能 runtime/ffmpeg 或指定 --ffprobe。')
    proc = subprocess.run([str(executable), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                          capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
    if proc.returncode:
        raise DownloadError('invalid_video', '文件无法由 ffprobe 读取，可能是错误页、密文或未完整下载。')
    data = json.loads(proc.stdout)
    video = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
    duration = float(data.get('format', {}).get('duration') or 0)
    if not video or not math.isfinite(duration) or duration <= 0 or path.stat().st_size < 1024:
        raise DownloadError('invalid_video', '文件没有有效视频流或时长。')
    audio = [s for s in data.get('streams', []) if s.get('codec_type') == 'audio']
    if require_audio and not audio:
        raise DownloadError('missing_audio', '目标视频应有声音，但文件缺少音轨；不将无声画面流当作完整原片。')
    if expected_duration is not None:
        if not math.isfinite(expected_duration) or expected_duration <= 0:
            raise DownloadError('invalid_expected_duration', '预期时长必须为正数。')
        if abs(duration - expected_duration) > duration_tolerance(expected_duration):
            raise DownloadError('duration_mismatch', '文件时长与已核实的完整作品时长不符。')
    # Decode short samples near the beginning and end; detect unusable ciphertext/truncation.
    decoder = Path(executable).with_name('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    if not decoder.is_file():
        raise DownloadError('missing_ffmpeg', 'ffprobe 同目录需要 ffmpeg，以验证媒体可以解码。')
    for position in dict.fromkeys((0, max(0, duration - 1))):
        result = subprocess.run([str(decoder), '-v', 'error', '-xerror', '-ss', str(position), '-i', str(path),
                                 '-t', '0.5', '-map', '0:v:0', '-map', '0:a:0?', '-f', 'null', '-'],
                                capture_output=True, timeout=60)
        if result.returncode:
            raise DownloadError('decode_failed', '媒体采样解码失败；不将该文件报告为下载成功。')
    return {'bytes': path.stat().st_size, 'duration_seconds': duration,
            'width': video.get('width'), 'height': video.get('height'), 'codec': video.get('codec_name'),
            'audio_streams': len(audio), 'audio_codecs': [s.get('codec_name') for s in audio]}

class QuietLogger:
    def debug(self, message):
        pass
    def warning(self, message):
        pass
    def error(self, message):
        pass

def douyin_download(url, stage, cookie_file=None, ffmpeg=FFMPEG, reuse=None):
    try:
        import yt_dlp
    except ImportError:
        raise DownloadError('missing_dependency', 'yt-dlp 依赖缺失，请检查技能 runtime/python-packages。')
    options = {'outtmpl': str(stage / 'video.%(ext)s'), 'format': 'best[ext=mp4]/best',
               'noplaylist': True, 'quiet': True, 'no_warnings': True, 'logger': QuietLogger(),
               'socket_timeout': 30, 'retries': 2, 'extractor_retries': 1,
               'ffmpeg_location': str(ffmpeg.parent), 'overwrites': False,
               'windowsfilenames': True}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            if cookie_file:
                # Only pass the relevant site cookies, in memory; never copy full browser credentials.
                jar = http.cookiejar.MozillaCookieJar()
                jar.load(str(cookie_file), ignore_discard=True, ignore_expires=False)
                for cookie in jar:
                    domain = cookie.domain.lstrip('.')
                    if domain == 'douyin.com' or domain.endswith('.douyin.com'):
                        ydl.cookiejar.set_cookie(cookie)
            # Resolve metadata once, then check identity before transferring media.
            info = ydl.extract_info(url, download=False)
            if not info or info.get('_type') in ('playlist', 'multi_video'):
                raise DownloadError('not_single_video', '该链接不是单条普通视频。')
            if reuse and info.get('id'):
                existing = reuse(str(info['id']))
                if existing:
                    return existing
            info = ydl.process_ie_result(info, download=True)
            path = Path(ydl.prepare_filename(info))
            if not path.is_file() or not path.resolve().is_relative_to(stage.resolve()):
                raise DownloadError('download_missing', '下载器未产生预期媒体文件。')
            return path, {'id': str(info.get('id') or fingerprint(url)),
                          'title': info.get('title') or '抖音视频', 'author': info.get('uploader') or ''}
    except DownloadError:
        raise
    except Exception as exc:
        # Do not surface raw signed URLs, cookies or extractor responses.
        message = str(exc).lower()
        if 'fresh cookies' in message or 'not necessarily logged in' in message:
            raise DownloadError('douyin_extractor_unavailable', '抖音提取接口未返回有效媒体信息；这不等于必须登录。请检查同一作品公开页面，并按网页备用路径取得完整音画。') from None
        if any(marker in message for marker in ('captcha', 'verification challenge', 'verify you are')):
            raise DownloadError('verification_required', '平台要求验证；由用户在网页完成，不自动绕过。') from None
        if '403' in message:
            raise DownloadError('access_denied', '媒体请求被平台拒绝（HTTP 403）；不据此认定必须登录。') from None
        if '429' in message:
            raise DownloadError('rate_limited', '平台限制请求频率；停止本条重试，稍后按授权范围恢复。') from None
        if any(marker in message for marker in ('login required', 'log in to', 'sign in to', 'login is required')):
            raise DownloadError('login_required', '平台明确要求登录；由用户完成抖音网页登录后再处理。') from None
        if any(marker in message for marker in ('getaddrinfo', 'name resolution', 'timed out', 'connection refused')):
            raise DownloadError('network_error', '网络连接或域名解析失败；先区分运行沙箱限制与平台故障。') from None
        raise DownloadError('douyin_parse_failed', '抖音下载失败：可能是链接失效、网络限制或平台解析规则变化。') from None

def video_id_from_url(url):
    """Only accepted direct video links have an identity available offline."""
    platform(url)
    match = re.fullmatch(r'/(?:share/)?video/([0-9]+)/?', urllib.parse.urlsplit(url).path)
    return match.group(1) if match else None


class SourceIndex:
    """Index filenames once per batch; verify media at every reuse."""
    def __init__(self, output):
        self.output = output.resolve()
        self.requests = {}
        self.videos = {}
        for video in output.iterdir():
            identity = re.fullmatch(r'抖音_.*_\[([^\[\]]+)\](?:_\d+)?\.[^.]+', video.name)
            if identity and video.is_file():
                self.add({'video_id': identity.group(1), 'file': video.name})
        # Read old records for compatibility; never create new sidecars.
        for sidecar in chain((output / '来源记录').glob('*.source.json'), output.glob('*.source.json')):
            try:
                record = json.loads(sidecar.read_text(encoding='utf-8'))
                if not isinstance(record, dict) or record.get('platform') != 'douyin':
                    continue
                # Older records embedded the extractor ID only in the filename.
                legacy = re.search(r'_\[([0-9]+)\](?:_\d+)?\.[^.]+$', record.get('file', ''))
                if not record.get('video_id') and legacy:
                    record['video_id'] = legacy.group(1)
                self.add(record)
            except (OSError, ValueError, TypeError):
                continue

    def add(self, record):
        for key, table in (('request_id', self.requests), ('video_id', self.videos)):
            value = record.get(key)
            if isinstance(value, str) and value:
                table.setdefault(value, []).append(record)

    def find(self, ffprobe, request_id=None, video_id=None, expected_duration=None, require_audio=False):
        candidates = self.videos.get(video_id, []) + self.requests.get(request_id, [])
        checked = set()
        for record in candidates:
            try:
                existing = self.output / record['file']
                if existing in checked:
                    continue
                checked.add(existing)
                if existing.resolve().parent != self.output or not existing.is_file():
                    continue
                return {'status': 'already_exists', 'platform': 'douyin',
                        'path': str(existing.resolve()), **probe(existing, ffprobe, expected_duration, require_audio)}
            except (OSError, ValueError, TypeError, KeyError, DownloadError):
                continue
        return None


def save_one(url, output, args, source_index=None):
    kind = platform(url)
    request_id = fingerprint(url)
    source_index = source_index if source_index is not None else SourceIndex(output)
    direct_id = video_id_from_url(url)
    supplied_id = getattr(args, 'video_id', None)
    if direct_id and supplied_id and direct_id != supplied_id:
        raise DownloadError('video_id_mismatch', '备用媒体的视频ID与源链接不一致。')
    known_id = direct_id or supplied_id
    manifest = getattr(args, 'browser_manifest', None)
    for auxiliary in (manifest, getattr(args, 'local_media', None)):
        if auxiliary:
            check_temporary_path(auxiliary)
    expected_duration = getattr(args, 'expected_duration', None)
    require_audio = bool(manifest) or getattr(args, 'require_audio', False)
    if manifest and (not known_id or not re.fullmatch(r'[0-9]+', known_id) or not expected_duration):
        raise DownloadError('browser_identity_required', '分轨清单须绑定明确的视频ID及当前播放器完整时长。')
    existing = source_index.find(args.ffprobe, request_id, known_id or request_id, expected_duration, require_audio)
    if existing:
        return existing
    with tempfile.TemporaryDirectory(prefix='social-video-download-', dir=temporary_parent(args)) as temporary:
        stage = Path(temporary)
        if manifest:
            path = import_stream_pair(manifest, stage, args.ffprobe, expected_duration)
            profile = {'id': known_id, 'title': args.title or '抖音视频', 'author': getattr(args, 'author', None) or ''}
        elif getattr(args, 'local_media', None):
            path = stage / ('video' + args.local_media.suffix)
            if not args.local_media.is_file():
                raise DownloadError('local_media_missing', '浏览器下载的本地媒体文件不存在。')
            shutil.copyfile(args.local_media, path)
            profile = {'id': known_id or request_id, 'title': args.title or '视频', 'author': ''}
        elif args.media_url:
            path = stage / 'video.mp4'
            media_download(args.media_url, path, referer='https://www.douyin.com/')
            profile = {'id': known_id or request_id, 'title': args.title or '抖音视频', 'author': ''}
        else:
            downloaded = douyin_download(url, stage, args.cookies_file, args.ffprobe.with_name('ffmpeg.exe'),
                                         lambda identity: source_index.find(args.ffprobe, video_id=identity,
                                                                            expected_duration=expected_duration,
                                                                            require_audio=require_audio))
            if isinstance(downloaded, dict):
                return downloaded
            path, profile = downloaded
            known_id = profile['id']
        verified = probe(path, args.ffprobe, expected_duration, require_audio)
        stem = safe_name('抖音_' + profile['title'])
        stem += '_[' + safe_name(profile['id'])[:32] + ']'
        destination = output / (stem + path.suffix)
        counter = 1
        # Hard-link promotion is exclusive, preventing overwrite even if another process races.
        while True:
            try:
                promote_exclusive(path, destination)
                break
            except FileExistsError:
                destination = output / (stem + f'_{counter}' + path.suffix)
                counter += 1
        source_index.add({'request_id': request_id, 'video_id': profile['id'], 'file': destination.name})
        return {'status': 'downloaded', 'platform': kind, 'path': str(destination.resolve()), **verified}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('text', nargs='*', help='分享链接或包含链接的分享文案')
    parser.add_argument('--input-file', type=Path, help='UTF-8 分享文案文件；避免 shell 转义问题')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--temp-dir', type=Path, help='项目任务暂存父目录；默认系统临时目录，禁止桌面')
    parser.add_argument('--cookies-file', type=Path, help='抖音 Netscape Cookie 文件')
    parser.add_argument('--ffprobe', type=Path, default=FFPROBE)
    media_group = parser.add_mutually_exclusive_group()
    media_group.add_argument('--media-url', help='从同一视频页面/API获得的媒体直链（只限单条源链接）')
    media_group.add_argument('--local-media', type=Path, help='已从同一目标视频页面下载的媒体；复验并复制入库')
    media_group.add_argument('--browser-manifest', type=Path, help='同一目标页面导出的音画分轨清单；地址只在本地使用')
    parser.add_argument('--video-id', help='备用模式中已核实的目标视频ID')
    parser.add_argument('--expected-duration', type=float, help='已核实的完整作品时长（秒）；用于拒绝预览片段')
    parser.add_argument('--require-audio', action='store_true', help='目标应有声音时启用；拒绝无声音画流')
    parser.add_argument('--title')
    parser.add_argument('--author', help='网页上已核实的发布者名称（可选）')
    parser.add_argument('--dry-run', action='store_true', help='只解析输入与目标路径；不联网、不创建目录')
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args(argv)
    if args.self_check:
        checks = {'python_supported': sys.version_info >= (3, 10)}
        details = {'python': sys.version.split()[0], 'python_executable': sys.executable,
                   'skill_root': str(SKILL_ROOT), 'default_output': str(DEFAULT_OUTPUT)}
        try:
            import yt_dlp.version
            import yt_dlp
            checks['yt_dlp_bundled'] = Path(yt_dlp.__file__).resolve().is_relative_to(VENDOR.resolve())
            details.update(yt_dlp=yt_dlp.version.__version__, yt_dlp_path=yt_dlp.__file__)
        except ImportError:
            checks['yt_dlp_bundled'] = False
        for name, executable in (('ffprobe', args.ffprobe), ('ffmpeg', args.ffprobe.with_name('ffmpeg.exe'))):
            details[name + '_path'] = str(executable)
            checks[name + '_exists'] = executable.is_file()
            try:
                result = subprocess.run([str(executable), '-version'], capture_output=True,
                                        text=True, encoding='utf-8', errors='replace', timeout=15)
                checks[name + '_runs'] = result.returncode == 0
                details[name + '_version'] = result.stdout.splitlines()[0] if result.stdout else ''
            except (OSError, subprocess.TimeoutExpired):
                checks[name + '_runs'] = False
        passed = all(checks.values())
        print(json.dumps({'passed': passed, **checks, **details}, ensure_ascii=False))
        return 0 if passed else 1
    text = '\n'.join(args.text)
    if args.input_file:
        try:
            check_temporary_path(args.input_file)
        except DownloadError as exc:
            print(json.dumps({'status': 'failed', 'code': exc.code, 'message': str(exc)}, ensure_ascii=False))
            return 1
        text += '\n' + args.input_file.read_text(encoding='utf-8-sig')
    links = extract_links(text)
    if not links:
        print(json.dumps({'status': 'failed', 'code': 'no_link', 'message': '未找到链接。请发送抖音视频分享链接或包含链接的分享文案。'}, ensure_ascii=False))
        return 1
    if (args.media_url or args.local_media or args.browser_manifest) and len(links) != 1:
        parser.error('媒体备用模式只能与单条源链接配合使用')
    output = args.output.resolve()
    results = []
    source_index = None
    for index, url in enumerate(links, 1):
        try:
            if args.dry_run:
                result = {'status': 'planned', 'platform': platform(url), 'output': str(output)}
            else:
                output.mkdir(parents=True, exist_ok=True)
                if source_index is None:
                    source_index = SourceIndex(output)
                result = save_one(url, output, args, source_index)
        except DownloadError as exc:
            result = {'status': 'failed', 'code': exc.code, 'message': str(exc)}
        except Exception as exc:
            result = {'status': 'failed', 'code': type(exc).__name__, 'message': '本地处理失败；检查目录权限、磁盘空间和运行依赖。'}
        results.append({'item': index, **result})
    print(json.dumps({'output': str(output), 'results': results}, ensure_ascii=False, indent=2))
    return int(any(result['status'] == 'failed' for result in results))

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
