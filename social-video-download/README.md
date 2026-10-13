# 抖音下载技能源码

2026-10-13：按实际视频ID查重，短链只解析一次元信息再下载；每批只扫描一次来源记录，复用文件仍做采样解码验证。兼容旧来源记录，不增加数据库。

本目录是源码与锁定依赖记录，不附yt-dlp/FFmpeg二进制，也不含Cookie、素材或本机安装状态。运行要求Python 3.10+。按`runtime/manifest.json`的记录，将对应版本yt-dlp放入`runtime/python-packages`，将FFmpeg/ffprobe放入`runtime/ffmpeg`；例如`python -m pip install --target runtime/python-packages yt-dlp==2026.8.19`。FFmpeg必须核对manifest中的工具哈希，不把发行商当前下载链接当作已锁定版本。

先运行`python scripts/download.py --self-check`；通过后用UTF-8分享文案文件执行`--input-file`。本机已安装目录无需重装依赖。跨机器的输出位置按任务指定`--output`。

最小离线验证：`python -m unittest discover -s tests -p test_download.py -v`。13项覆盖真实本地音画采样、重复链接、同视频不同链接、批量单次索引、旧记录、损坏媒体重下、防覆盖及错误页；平台解析模拟，无外网请求。本轮没有重新下载真实抖音视频，真实平台可用性留待具体任务验证。
