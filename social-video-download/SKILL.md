---
name: social-video-download
description: 根据用户发送的抖音视频分享链接，将视频下载到本地电脑的视频分析池。支持单条、批量链接及包含链接的分享文案。仅分析已有文件、讨论视频内容或发送其他平台链接时不自动下载。
---

# 抖音分享链接下载

默认保存到 `D:/Codex项目文件夹/视频制作/素材`。当次明确指定其他目录时遵循用户要求。只下载链接对应的视频，不展开账号、合集、收藏或推荐流，不自动分析、上传或发送素材。

## 执行

入口 [scripts/download.py](scripts/download.py)。支持 `v.douyin.com` 短链、抖音视频页面和含 `modal_id` 的分享页面；批量提取、去重，单条失败后继续其他条目。

优先使用 Codex 自带 Python：`C:\Users\lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`。路径不存在时用 `load_workspace_dependencies` 定位。

先执行 `--self-check`。把用户原始分享文案写入任务的 UTF-8 临时文件，用 `--input-file <绝对路径>` 传入，避免将用户文案插入 shell 代码。用户发链接并表达下载意图即可执行，不重复询问保存目录。

下载库随技能放在 `runtime/python-packages`，FFmpeg及ffprobe放在 `runtime/ffmpeg`，均按技能自身位置定位，不依赖构建项目目录。Python复用Codex自带运行环境，要求3.10及以上；不修改系统Python、PATH或其他技能环境。版本与来源见 `runtime/manifest.json`。`--self-check`会检查下载库来自本技能，并实际启动两个媒体工具；失败时先修复依赖再下载。

## 失败与网页备用

处理登录、Cookie或提取失败时读 [references/platforms.md](references/platforms.md)。`douyin_extractor_unavailable`不能直接证明网页必须登录；允许访问的公开页面能播放时，使用Edge插件取得同一视频，再用`--local-media`验证入库。若播放器为Blob且音画分轨，按[分轨备用操作](references/browser-streams.md)取得当前作品的媒体清单，用`--browser-manifest`下载并按原编码合并。用户始终只需提供分享链接；媒体直链、清单和本地暂存文件是内部步骤。

只使用用户授权的抖音站点登录态，不打印Cookie或签名媒体URL，不读取无关站点数据。登录、扫码、验证码由用户完成。工具明确拒绝目标并禁止绕过时停止该目标，不换路径实现同一访问。

## 验证与交付

临时目录下载，ffprobe检查视频流、音轨和时长，再用FFmpeg解码开头和结尾采样；通过后无覆盖保存为 `抖音_标题_[视频ID].扩展名`。网页备用须用`--expected-duration`核对完整时长；目标有声时加`--require-audio`，不把无声画面轨或预览片段当原片。分轨模式自动要求音轨。按实际视频ID查重，不同分享链接指向同一视频时也复用；短链先解析元信息，命中已有记录则不下载媒体。已有文件按当次声音/时长要求复验，每条视频保留不含凭据的`.source.json`。批量只扫描一次来源记录，并随成功下载更新内存索引，不增加长期数据库；旧记录仍兼容。

保留来源编码和声音，不承诺无水印或原画，不放大画质。采样验证不等同于逐帧完整检查。最终用中文给出成功/失败数量、可点击的本地文件路径和真实阻塞项。只清理本次输入、确认无用的暂存文件，不删除已下载视频。
