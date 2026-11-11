---
name: local-video-production
description: 按视频需求自主组合本地剪辑、二维或三维动画与素材制作，生成并交付本地视频；工具和云端素材按需选择。
---

# 本地视频制作

按用户目标、已有素材和当前授权选择工具，直接完成合适的制作、合成与交付。没有固定工具顺序或必经的生成、下载、转写、预览步骤；单项编辑可直接使用本地入口。仅对影响成片的关键歧义询问，其他合理推断。

默认成片短边1080像素：画幅沿用户素材的显示比例，常见横屏1920×1080、竖屏1080×1920、方形1080×1080；只按用户要求调整清晰度或画幅。没有素材且用户未指定画幅时先确认；多段素材比例不一致时以用户明确要求为准，关键处理方式无法判断时先对齐。用户要求保留原规格时遵从要求，不把1080p当上限。H.264/yuv420p导出宽高须为正偶数；低清素材放大不能当作新增细节。输出和过程资料归本次指定的制作目录，不覆盖已有正式文件。

## 按需选择

- 剪辑、拼接、字幕、调色、混音和封装：复用`video-use`入口或直接用FFmpeg；需要精确切点、保留原规格等按实际选择。FFmpeg/ffprobe在`C:/Users/lenovo/AppData/Local/Programs/FFmpeg/bin/`。
- 二维动画：Remotion及HTML/CSS/Canvas；SVG用于矢量图、图表和图形动画；Python、Pillow、NumPy可制作或处理图片及序列。选择适合的方式，不强制混用。
- 三维：Blender制作场景、模型与动画；Three.js制作实时场景，可结合Remotion的ThreeCanvas渲染。作品场景及动画使用任务指定的画布，默认按素材比例和1080p设置；Blender后台入口可用`--width <宽> --height <高>`临时指定输出尺寸，不改源`.blend`。交互操作使用当前会话MCP并核对连接，仅在需要时启动。
- 图片：需要AI图片时用当前会话可用的ImageGen生成或编辑，作为素材保存到本次项目；它是云端能力并受账户额度约束。
- 素材下载：仅根据用户提供或明确指定的来源下载；抖音可用`C:/Users/lenovo/.codex/skills/social-video-download/scripts/download.py --input-file <分享文案绝对路径> --output <目录>`，通过下述宿主Python运行；其他支持的网站可用宿主`yt-dlp`。
- 旁白、配乐、音效或转写：优先复用已有音频或转写；需要时可使用已接入的火山TTS、Seed-Audio和ASR。视频生成等高成本调用、批量生成或预计费用明显较高时，先说明预计调用与可能费用并确认；成本无法合理判断时先询问，已有明确确认不重复询问。不打印凭据、不静默重复提交；未知状态沿原任务恢复。

## 本地入口

宿主Python：`C:/Users/lenovo/AppData/Local/Programs/VideoTools/.venv/Scripts/python.exe`。共享入口：`C:/Users/lenovo/.codex/runtimes/personal-video/video-toolchain/video-tools.ps1`。

明确切点可写UTF-8 EDL后调用：

```powershell
& 'C:/Users/lenovo/.codex/runtimes/personal-video/video-toolchain/video-tools.ps1' video-use '<EDL绝对路径>' '<输出绝对路径>'
```

EDL最小结构为`{"version":1,"sources":{"a":"D:/素材.mp4"},"ranges":[{"source":"a","start":0,"end":2}]}`；明确指定尺寸时添加`"canvas":[宽,高]`。可加`subtitles`的SRT路径、`overlays`及`grade`；默认等比缩放补边，全屏叠加按目标画布准备，需特定位置或缩放的局部叠加可用FFmpeg。`--draft`按比例缩至短边最多720像素；仅截取且其他规格须保持不变时可直接用FFmpeg。

`video-tools.ps1`还提供`compositions`、`remotion-render`、`production`和`blender start/status/render/verify`；共享Remotion渲染入口仅针对共享注册组件，作品自有动画放作品工程，用共享依赖或作品隔离依赖渲染。共享Remotion模块位于`C:/Users/lenovo/.codex/runtimes/personal-video/video-toolchain/remotion/node_modules/`；外部作品配置webpack模块解析以保留原路径并指向该目录。ThreeCanvas使用帧驱动动画、明确width/height和`--gl=angle`，勿依赖实时累计帧。

火山语音与音效可通过`C:/Users/lenovo/.codex/runtimes/personal-video/run_api.py production_cloud`调用：先用`prepare tts|audio <请求JSON> <新任务目录>`本地准备，再按有效授权`submit <任务目录> --allow-paid-calls`；`status`查状态。TTS请求包含`req_params.text`、`speaker`、`audio_params.format=mp3`；Seed-Audio请求包含`model=seed-audio-1.0`、`text_prompt`和`audio_config`。需要转写时使用已接入ASR工作流；提交未知不重试。

根据目标核对实际尺寸、时长、声音、画面和同步；技术解码成功不等于视觉或听感验收。只调用本次必要的工具和服务，失败保留恢复所需状态。
