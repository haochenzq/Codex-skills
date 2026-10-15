# 抖音下载技能源码

2026-10-15：补充分离音视频流的浏览器清单导入、完整时长与音轨核验，纠正提取器Cookie提示的误分类。操作见[浏览器备用流程](references/browser-streams.md)。

2026-10-13：按实际视频ID查重，短链只解析一次元信息再下载；每批只扫描一次来源记录，复用文件仍做采样解码验证。兼容旧来源记录，不增加数据库。

本目录是源码与锁定依赖记录，不附yt-dlp/FFmpeg二进制，也不含Cookie、素材或本机安装状态。运行要求Python 3.10+。按`runtime/manifest.json`的记录，将对应版本yt-dlp放入`runtime/python-packages`，将FFmpeg/ffprobe放入`runtime/ffmpeg`；例如`python -m pip install --target runtime/python-packages yt-dlp==2026.8.19`。FFmpeg必须核对manifest中的工具哈希，不把发行商当前下载链接当作已锁定版本。

先运行`python scripts/download.py --self-check`；通过后用UTF-8分享文案文件执行`--input-file`。本机已安装目录无需重装依赖。跨机器的输出位置按任务指定`--output`。

最小离线验证：`python -m unittest discover -s tests -p test_download.py -v`。20项检查覆盖去重、防覆盖、错误分类、清单来源校验、音视频分离合并、时长及音轨要求；使用模拟网络和本地生成媒体，不发起真实平台请求。2026-10-15另有4条用户授权原片通过已安装入口、全片音画解码及重复下载复用验证；这是这4条样本的结果，不保证所有抖音页面始终可下载。
