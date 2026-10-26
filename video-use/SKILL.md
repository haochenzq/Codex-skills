---
name: video-use
description: 执行明确切点或操作的剪切、字幕、调色、混音、叠加等视频编辑。
---

# 单项视频编辑

复用素材、切点和字幕；明确编辑不强制转写。

## 入口与EDL

入口：`C:/Users/lenovo/.codex/runtimes/personal-video/video-toolchain/video-tools.ps1`。
调用：`video-tools.ps1 video-use <EDL绝对路径> <输出绝对路径>`；局部低清预览加`--draft`。只查所需依赖，复用有效结果；全量`doctor`仅用于部署验收或无法定位的故障。共享依赖不兼容时可在作品内隔离。

```json
{"version":1,"sources":{"take1":"D:/素材.mp4"},"ranges":[{"source":"take1","start":2.4,"end":6.8}]}
```

start/end为原片秒数，ranges顺序即成片顺序。可选：`subtitles`为成片时间SRT绝对路径；`overlays`如`[{"file":"D:/动画.webm","start_in_output":0,"duration":2}]`；`grade`为预设或FFmpeg滤镜。

未指定canvas沿首素材朝向；合成器仅1080p横/竖屏、预览720p，等比补边。其他规格或仅截取且其余不变时用FFmpeg，避免默认响度、淡化或分辨率改变输出。

FFmpeg/ffprobe：`C:/Users/lenovo/AppData/Local/Programs/FFmpeg/bin/`；Python：`C:/Users/lenovo/AppData/Local/Programs/VideoTools/.venv/Scripts/python.exe`；helpers在本技能目录。不借Codex内部依赖，只给子进程配置媒体路径；少用参数查`--help`。

## 编辑与验证

- 语义选段核对完整原话和原片，不按静音或模型估时机械删减；切口避开词内，按听感留呼吸。流复制受关键帧限制，精确边界需重编码受影响部分。
- 字幕按`output_time=word.start-segment_start+segment_offset`重排，中文不逐词加空格。复制指定段落到开头时保留原位置，用真实源区间并重排字幕，不用静帧或猜切点。
- 动画用`setpts=PTS-STARTPTS+T/TB`定位，透明叠加保留alpha，缓存匹配素材与配置。调色、叠加、字幕尽量合并处理，HDR转SDR须色调映射。
- 混音尽量用PCM中间轨，响度处理一次，音效瞬态对齐动作。核对实际画幅、字体、安全区、声音及同步，仅不确定项作局部预览。

## 旁白＋配乐预设

本次未指定时的个人起始基准：整体−20 LUFS（±0.4），旁白高配乐4 LU（±0.5），自动闪避0 dB，编码后真峰值≤−1.5 dBTP；非平台标准。

按BS.1770/EBU R128测最终声道，同一有效旁白区间比较声部，单声道先复制双声道。稳定轨道增益，轻背景先规范化，混音后整体恒定增益；不默认EQ、压缩或拉伸，测量不代替听辨。
