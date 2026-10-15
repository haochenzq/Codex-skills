"""Import the two streams observed on one authorized Douyin player page."""
import json
import math
from pathlib import Path
import subprocess
import urllib.parse

from download_errors import DownloadError
from media_downloader import media_download


def stream_info(path, ffprobe):
    result = subprocess.run([str(ffprobe), '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', str(path)], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=60)
    if result.returncode:
        raise DownloadError('invalid_stream', '下载的媒体轨无法读取，不作为完整视频入库。')
    try:
        data = json.loads(result.stdout)
        duration = float(data.get('format', {}).get('duration') or 0)
    except (ValueError, TypeError):
        raise DownloadError('invalid_stream', '媒体轨元信息无效。') from None
    if not math.isfinite(duration) or duration <= 0:
        raise DownloadError('invalid_stream', '媒体轨没有有效时长。')
    return data.get('streams', []), duration


def duration_tolerance(expected):
    return max(0.5, expected * 0.002)


def read_manifest(path):
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise DownloadError('invalid_browser_manifest', '媒体清单过大；只导出当前视频的两条媒体轨。')
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        entries = data.get('assets', []) + data.get('failures', [])
        selected = {'video': [], 'audio': []}
        for item in entries:
            if not isinstance(item, dict):
                continue
            name = item.get('name', '')
            kind = 'video' if name.startswith('media-video-') else 'audio' if name.startswith('media-audio-') else None
            if not kind:
                continue
            url = item.get('url', '')
            parsed = urllib.parse.urlsplit(url)
            host = (parsed.hostname or '').lower()
            if (parsed.scheme != 'https' or not host.endswith('.douyinvod.com')
                    or parsed.username or parsed.password or parsed.port not in (None, 443)):
                raise ValueError('Untrusted stream source')
            if url not in selected[kind]:
                selected[kind].append(url)
        if any(len(urls) != 1 for urls in selected.values()):
            raise ValueError('Ambiguous or missing stream pair')
        if selected['video'] == selected['audio']:
            raise ValueError('Identical stream sources')
    except (ValueError, TypeError, AttributeError):
        raise DownloadError('invalid_browser_manifest', '清单必须只包含同一目标视频的一条画面轨和一条音轨；请重新核对页面后导出。') from None
    return {kind: urls[0] for kind, urls in selected.items()}


def import_stream_pair(manifest, stage, ffprobe, expected_duration):
    if not expected_duration or not math.isfinite(expected_duration) or expected_duration <= 0:
        raise DownloadError('expected_duration_required', '分轨下载须提供当前播放器已核实的完整时长。')
    urls = read_manifest(manifest)
    paths = {kind: stage / (kind + '.mp4') for kind in ('video', 'audio')}
    for kind, path in paths.items():
        media_download(urls[kind], path, referer='https://www.douyin.com/')
        streams, duration = stream_info(path, ffprobe)
        if not any(s.get('codec_type') == kind for s in streams):
            raise DownloadError('wrong_stream_type', '导出的媒体类型与所选画面/声音轨不对应。')
        if abs(duration - expected_duration) > duration_tolerance(expected_duration):
            raise DownloadError('duration_mismatch', '媒体轨时长与播放器不符，可能只下载到片段或选错作品。')
    target = stage / 'video-muxed.mp4'
    ffmpeg = Path(ffprobe).with_name('ffmpeg.exe' if Path(ffprobe).suffix == '.exe' else 'ffmpeg')
    result = subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
                             '-i', str(paths['video']), '-i', str(paths['audio']),
                             '-map', '0:v:0', '-map', '1:a:0', '-c', 'copy',
                             '-movflags', '+faststart', str(target)], capture_output=True, timeout=120)
    if result.returncode:
        raise DownloadError('stream_mux_failed', '音画原编码合并失败；未将分轨或不完整文件入库。')
    return target
