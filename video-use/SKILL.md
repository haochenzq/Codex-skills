---
name: video-use
description: 视频制作与LibTV制作共用：切点与操作已明确的剪切、字幕、调色、混音或叠加等单项编辑自动使用；按任务所属项目读取要求。helpers、运行器及manim-video保持通用。
---

# 本地视频剪辑工具

本技能的双项目共用范围只限定工作流指令。`helpers/`、共享运行器及 `skills/manim-video/` 保持原位置与跨项目通用适用范围；其他既有调用直接使用所需模块或Manim入口，不因此加载本项目要求。不重复整套制作访谈、选段、动画分工和审批流程。


## 项目范围与规则

本技能服务 `D:/Codex项目文件夹/视频制作` 与 `D:/Codex项目文件夹/LibTV制作`，按任务归属判断，不仅看当前工作目录。其他项目仅在明确承接其中一个制作项目的任务时沿用其要求；两项目不互相继承专属偏好。源码与全局安装位置不变。

执行前按任务所属读取[视频制作入口](D:/Codex项目文件夹/视频制作/AGENTS.md)或[LibTV制作入口](D:/Codex项目文件夹/LibTV制作/AGENTS.md)读取当前操作对应的规则，已读且未变内容直接复用。操作前只读本次剪切、字幕、调色或叠加涉及的要求与参数，不展开整片创作方案。发布或交付配套时读发布规则，收尾读项目文件整理规则。项目文件维护要求与参数，技能只维护执行方法；共享运行说明提供技术入口与限制，不另设业务要求。

## 路由与运行

- 明确切点或单项编辑直接执行本技能，不要求用户点名；仅视频制作的口播任务需要判断原声音画口播的删留、口误、重录、重复及停顿时，使用 [talking-head-editing](C:/Users/lenovo/.codex/skills/talking-head-editing/SKILL.md) 的选段与必要检查流程，再复用本技能合成。
- 视频制作的本地整片创作、动画或复杂合成：使用 [toolchain-video-production](C:/Users/lenovo/.codex/skills/toolchain-video-production/SKILL.md) 组织制作；简单且已明确的单项编辑直接执行。LibTV整片继续由libtv-drama-production统筹，不切换到排除Seedance的本地整片路线；对白取舍按已确认剧本，实质改写回编剧导演。
- 仅分析或转写：使用 [volc-video-analysis](C:/Users/lenovo/.codex/skills/volc-video-analysis/SKILL.md)。需要Manim时再读 [Manim入口](C:/Users/lenovo/.codex/skills/video-use/skills/manim-video/SKILL.md)。

本机先按需读取 [统一运行入口](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md)，使用其中 `video-toolchain/video-tools.ps1` 的 `video-use`、`timeline` 或 `manim` 命令。首次使用、依赖变化或报错时检查 `doctor`；同一任务复用正常环境。该入口适配Windows中文路径、静音源、PCM中间音轨、透明叠加与横竖画布；不在作品中重复安装依赖。

本包 `README.md`、`install.md`、`SKILL.upstream.md` 和附带Manim的README/setup属于上游说明，不是本机安装或运行入口；其中系统PATH、临时安装和ElevenLabs流程不得覆盖上述已部署路径。不要直接使用任意Python调用helpers；未被共享入口封装的辅助命令，先按技术参考配置实际解释器及子进程媒体路径。

合成调用：`video-tools.ps1 video-use <EDL绝对路径> <输出绝对路径>`；低清预览加 `--draft`。仅有兼容原版词级转写时才用 `--build-subtitles`。中文口播沿用口播技能生成的主字幕，避免套用原版英文双词、大写分行。完整数据与接口见 [技术参考](references/editing-techniques.md)。

仅截取且要求其他不变时，使用支持保留原规格与声音处理设置的直接FFmpeg路径，不套用默认合成适配器的1080p画布、响度处理和接缝淡化。精确切点与无损复制是否兼容，按素材关键帧和输出要求判断。

## 最小执行流程

1. 读取当前素材及已有编辑记录，核对目标、格式和已有转写/字幕。用户已明确的编辑动作直接执行，只有影响结果的关键缺口或新增范围才询问。
2. 按实际需要准备EDL、字幕或动画；已有有效证据直接复用。无语音、仅调色或已有可用字幕的任务不强制转写；精细语音剪接才需要保留原话的词级时间戳。本机按分析技能使用豆包ASR，不默认调用ElevenLabs。并发及代理分工遵循当次授权，不强制创建agent。
3. 直接渲染目标版本，不默认低清预览或完整预审；只有具体不确定项确需确认时才按需预览局部。
4. 按[一次必要检查](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md#一次必要交付检查)复用程序结果，仅查本次改动或明确异常；修复明确故障后只补查受影响部分，然后交付；收尾与过程文件按公共运行说明执行。

素材不覆盖；产物按用户指定位置或当前项目规则归位，缺少约定时使用本次任务目录，避免覆盖已有成果。过程位置与清理按公共运行说明执行。仅实际未完成的任务记录必要断点，沿用已有项目权威文件，不额外创建 `project.md`。

## 必须保持的剪辑正确性

- 语音剪口不落在词内，按实际听感保留呼吸和余量；30–200ms仅作起点，不固定套用。片段边界短淡入淡出消除爆音，不能截断音节。
- 片段提取后采用兼容参数无损拼接；调色在提取阶段处理，叠加和字幕合并到最后一次合成，避免无必要重复编码。
- 动画窗口使用 `setpts=PTS-STARTPTS+T/TB` 对齐，透明素材保留alpha；字幕最后烧录，按输出时间轴重排：`output_time = word.start - segment_start + segment_offset`。
- 时间戳和缓存绑定原素材及配置；不能把模型估计时间当词边界。素材或所需转写配置变化时才重做受影响证据。
- 核对实际字体、HDR到SDR映射、画幅及字幕安全区；以本次输出为准，不把工具自带英文样式或历史样片作为固定视觉方案。
