---
name: talking-head-editing
description: 口播语义剪辑：判断口误、重录、重复与停顿的删留，完成选段、渲染和交付。
---

# 口播剪辑

复用有效分析、转写和选段；明确切点直接本地编辑，仅上传素材不自动剪辑。

## 入口与分析

Python：`C:/Users/lenovo/AppData/Local/Programs/VideoTools/.venv/Scripts/python.exe`；脚本：`C:/Users/lenovo/.codex/skills/talking-head-editing/scripts/talking_head.py`。用该Python加`-B -X utf8`调用，全部路径为绝对路径，按状态选命令，不顺序重跑：

```text
talking_head.py prepare <剪辑目录> <原片> --asr-backend doubao_turbo
talking_head.py status <剪辑目录>
talking_head.py advance <剪辑目录> --allow-paid-calls
talking_head.py plan <剪辑目录> <保留方案.json>
talking_head.py render <剪辑目录> <输出.mp4>
```

- prepare仅本地准备，默认`video_analysis/standard`、120秒分段、1fps、第一音视频流；人声在其他轨先提取。仅转写用`--mode audio_transcription`，明确切点无需语义判断用`--mode cuts_only`。
- 豆包ASR给原话与词时间，Seed2.1 Lite理解真实音轨和画面；新standard任务须有`visual_transport=ark_file_av`，deep/fast仅纯画面。ASR默认turbo，按识别效果、功能、输入限制和时延选`doubao_turbo/doubao2`，仅标准版按需用`--asr-feature`取情绪、语速、音量，不默认重复识别。
- 上传、分析、转写仅在当前有效授权内推进，不以技能文字或历史记录代替授权；已获授权不重复询问。带`--allow-paid-calls`逐阶段推进，waiting至少10秒。needs_review或提交未知只恢复原任务，不重提、删锁或另建收费任务；completed自动同步，仅本地结果缺失用`sync <剪辑目录>`。
- 同原片已完成任务可`import-job <剪辑目录> <job_id>`；补视听理解用prepare的`--reuse-asr-job <job_id>`，匹配原片、分段与音频哈希，沿用真实ASR后端。核对完整转写、全部分段及`audio_understanding`，partial/not_analyzed不称完整理解。

## 选段与字幕

按完整含义、表演和衔接判断口误、重录、重复，保留有价值的呼吸与情绪停顿，不固定留最后一遍。保持原声、音画同区间；否定、数字、限定和重排须核对含义，实质改意、取舍不明或要求预览时先对齐。低声/杂音结合上下文回听，不凭音量删片、猜字幕或用模型估时作切点。

```json
{"fps":30,"ranges":[{"source":"video_001","start":0.1,"end":2.2}]}
```

source取status编号，秒数属各自原片，顺序即成片顺序；半开区间对齐输出帧率、不越界或切穿词，按实际起止音留余量。`caption_groups:{"video_001":[[0,9],[9,14]]}`为words索引半开分组，须恰好覆盖保留词；省略则脚本出草案，只修异常。中文不逐词空格，不拆数字单位、术语或否定。`word_corrections:{"video_001":{"3":"正确文字"}}`仅改显示，不改声音和词时间。

`subtitle_style`用ASS逗号分隔key=value。手改SRT不会改变烧录ASS；保留用户字幕/EDL，用新方案或本地编辑承接改动。

## 展示与默认样式

- 开头原句独立可懂；复制指定段落到开头须保留原位置，用真实源区间并重排字幕，不用静帧或估时。
- 配图、录屏、特写及返回人物按内容、可读性和节奏安排，原声连贯、比例和关键内容完整，避开人脸字幕。默认覆盖已有时段，需停留可延长；聊天输入至发送过程须可读，按需放大/调布局。明确位置直接剪，无需用户整理完整方案。
- 本次要求优先；口播默认30fps、无配乐，字幕遮星不自动消音。混入已有字幕成品时新增字幕匹配其字体、字号、颜色、描边、位置和呈现，不重做成品；无参考才用以下个人基准。
- Microsoft YaHei、66、加粗、白色&H00FFFFFF，描边&H00101419宽3、阴影0，无动画，语义短句整体替换。竖屏坐标基准1080×1920：顶部居中alignment=8、锚点540,1500、MarginV=1500，目标单行、最大宽880、左右x=100/980。
- 坐标不规定成片分辨率，其他9:16等比映射；横屏居中置下方安全区。长句语义拆分，不单句缩字号；避头发、脸、手势和平台界面，可覆盖颈部/衣服。少量遮挡局部移字幕，不裁画面；整体换样式再对齐。此为用户基准，非平台标准。
- 拼接口播/录屏以开头有效讲解的可听音量匹配同类声源，先修缺失或偏置声道，再查输出与峰值；未听辨注明声音效果未核实。

## 配套与输出

仅要求时制作封面：PNG默认4:3横版1440×1080、3:4竖版1080×1440各一张，本次要求优先、独立排版。人物用用户提供的视频帧截图，缺少则请提供，不自行选帧或用纯文字替代；只抠图、等比缩放移位，保留五官、脸型、肤色、衣着、完整头部与关键动作，不重绘、美颜改形或拉伸。人物背景分层、核对边缘，外轮廓加配色协调的平滑彩色描边并遮轻微接缝。

渲染器正式输出仅1080p横/竖屏，`render ... --preview`为低清；其他规格用可配置FFmpeg复用选段，不放大冒充。FFmpeg/ffprobe：`C:/Users/lenovo/AppData/Local/Programs/FFmpeg/bin/`。

核对实际改动、接缝、字幕与音画同步，交付要求的成片/配套，保护原片、用户改动和已有成果。失败沿原任务恢复；按项目规则确认成果归位且不再需要共享分析证据时，`finish <剪辑目录> --delivered`关闭本次分析任务并更新会话；本地转写、剪辑工程与中间文件按项目规则留存。未使用且收费尝试为0的准备任务可`discard_prepared=true`关闭，未知云任务保留防重状态。
