"""Download a resolved media stream, independently of platform authentication."""
from __future__ import annotations

import shutil
import urllib.error
import urllib.parse
import urllib.request

from download_errors import DownloadError

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'

def media_download(url, target, referer=None, headers=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise DownloadError('invalid_media_url', '解析返回的媒体地址不合法。')
    request_headers = {'User-Agent': UA}
    if referer:
        request_headers['Referer'] = referer
    for name, value in (headers or {}).items():
        if name.lower() not in ('user-agent', 'referer', 'origin', 'accept') or not isinstance(value, str):
            raise DownloadError('invalid_media_headers', '媒体下载仅接收必要请求头，不接收解析站点登录 Cookie。')
        if any(c in name + value for c in '\r\n'):
            raise DownloadError('invalid_media_headers', '媒体请求头格式不正确。')
        request_headers[name] = value
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response, target.open('xb') as output:
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' in content_type or 'application/json' in content_type:
                raise DownloadError('not_media', '媒体地址返回了网页或 JSON。')
            shutil.copyfileobj(response, output, 1024 * 1024)
            expected = response.headers.get('Content-Length')
            if expected and output.tell() != int(expected):
                raise DownloadError('incomplete_download', '下载长度与平台声明不一致。')
    except urllib.error.HTTPError as exc:
        raise DownloadError('media_http_error', f'媒体下载返回 HTTP {exc.code}；需重新解析媒体地址。') from None
    except (urllib.error.URLError, TimeoutError):
        raise DownloadError('media_network_error', '媒体下载网络失败或超时。') from None
