---
name: social-video-download
description: 用户要求下载抖音分享视频时，将单条或批量链接对应的视频保存到本地。
---

# 抖音视频下载

只下载指定作品到本次输出目录，不扩展账号、合集，不自动分析或上传。

## 下载入口

脚本：本技能`scripts/download.py`；Python：`C:/Users/lenovo/AppData/Local/Programs/VideoTools/.venv/Scripts/python.exe`，yt-dlp装在该环境；FFmpeg/ffprobe：`C:/Users/lenovo/AppData/Local/Programs/FFmpeg/bin/`。缺依赖时修复宿主安装或用完整兼容环境，不借Codex内部依赖或复制到技能目录；首次、依赖变化或报错时才`--self-check`。

分享文案写入UTF-8临时文件，安全传参，不拼成可执行代码：

```text
download.py --input-file <分享文案绝对路径> --output <输出绝对目录>
```

支持短链、视频页、modal_id页，批量提取并按ID去重；单条失败继续其余。默认系统临时目录，必要时用`--temp-dir <任务暂存目录>`。

## 网页备用

- 提取失败先在已授权Edge核对同一作品能否播放及ID、标题、发布者、完整时长，不据此要求登录。
- 用`--media-url <已观察URL>`或`--local-media <本地导出>`，配合单条分享输入及`--video-id`、`--title`、`--expected-duration`；有声目标加`--require-audio`。导出先确认落点，用任务暂存位置，不改全局下载设置。
- Blob分轨须在独立任务标签确认唯一目标画面轨和音轨，按资产导出能力生成manifest，以`--browser-manifest <绝对路径>`和上述元信息导入。若仅支持video资产，可把已观察的两条URL临时置为video元素，按原assetId导出后恢复或关闭标签。能力不足换受支持方式，身份不明先核实，不猜URL、签名或轨道配对。
- 登录、扫码、验证码由用户完成，必要时用其提供的`--cookies-file`；不打印Cookie、签名URL或清单全文，不读无关站点数据，明确访问拒绝时停止。

## 验证与交付

脚本经临时下载、ffprobe轨道/时长检查及首尾解码后，无覆盖保存为`抖音_标题_[视频ID].扩展名`；分轨按原编码合并、要求音轨，不用shortest截断。网页备用核对完整时长和声音，预览或无声画面不能充当原片。

复验同ID已有文件是否符合本次要求；保留来源编码与文件名ID，交付视频、成功/失败数量及路径，不另建来源台账或承诺无水印、画质提升。未完成下载保留必要恢复材料。
