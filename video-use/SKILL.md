---
name: video-use
description: 复用本地helpers进行视频剪接、调色、字幕与动画叠加。录制口播智能剪辑优先talking-head-editing，整片制作优先toolchain-video-production；本技能提供底层剪辑工具与按需技术说明。
---

# 本地视频剪辑工具

本技能的 `helpers/` 是现有口播及工具链制作流程的底层依赖，`skills/manim-video/` 提供数学与技术动画能力。保留这些代码，直接编辑请求也可使用；不再单独重复整套制作访谈、选段、动画分工和审批流程。

## 路由与运行

- 原声音画口播的口误、重录、重复及停顿处理：使用 [talking-head-editing](../talking-head-editing/SKILL.md) 的选段与听审流程，再复用本技能合成。
- 通用素材剪辑、整片制作或动画：使用 [toolchain-video-production](../toolchain-video-production/SKILL.md) 组织制作；简单且已明确的单项编辑直接执行。
- 仅分析或转写：使用 [volc-video-analysis](../volc-video-analysis/SKILL.md)。需要Manim时再读 [Manim入口](skills/manim-video/SKILL.md)。

本机先按需读取 [统一运行入口](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md)，使用其中 `video-toolchain/video-tools.ps1` 的 `video-use`、`timeline` 或 `manim` 命令。首次使用、依赖变化或报错时检查 `doctor`；同一任务复用正常环境。该入口适配Windows中文路径、静音源、PCM中间音轨、透明叠加与横竖画布；不在作品中重复安装依赖。

合成调用：`video-tools.ps1 video-use <EDL绝对路径> <输出绝对路径>`；低清预览加 `--draft`。仅有兼容原版词级转写时才用 `--build-subtitles`。中文口播沿用口播技能生成的主字幕，避免套用原版英文双词、大写分行。完整数据与接口见 [技术参考](references/editing-techniques.md)。

## 最小执行流程

1. 读取当前素材及已有编辑记录，核对目标、格式和已有转写/字幕。用户已明确的编辑动作直接执行，只有影响结果的关键缺口或新增范围才询问。
2. 按实际需要准备EDL、字幕或动画；已有有效证据直接复用。无语音、仅调色或已有可用字幕的任务不强制转写；精细语音剪接才需要保留原话的词级时间戳。本机按分析技能使用豆包ASR，不默认调用ElevenLabs。并发及代理分工遵循当次授权，不强制创建agent。
3. 渲染需要的版本。简单编辑可直接输出；复杂叠加、版式或不确定接缝先验证局部短片，必要时再整段预览，不固定生成低清片、全片预览和多轮复审。
4. 核对输出媒体流、时长、画幅及本次变动处：剪口听接缝，字幕看时间与遮挡，动画看入出点；检查结尾完整性。发现问题只修受影响处，再交付成片及需要的工程文件。

素材不覆盖；产物放在用户指定目录，未指定时用素材工程的 `edit/`，版本文件避免覆盖正式成片。复杂、未完成或需接续的任务记录关键决定、产物与下一步，沿用已有项目权威文件，不每次额外创建 `project.md`。

## 必须保持的剪辑正确性

- 语音剪口不落在词内，按实际听感保留呼吸和余量；30–200ms仅作起点，不固定套用。片段边界短淡入淡出消除爆音，不能截断音节。
- 片段提取后采用兼容参数无损拼接；调色在提取阶段处理，叠加和字幕合并到最后一次合成，避免无必要重复编码。
- 动画窗口使用 `setpts=PTS-STARTPTS+T/TB` 对齐，透明素材保留alpha；字幕最后烧录，按输出时间轴重排：`output_time = word.start - segment_start + segment_offset`。
- 时间戳和缓存绑定原素材及配置；不能把模型估计时间当词边界。素材或所需转写配置变化时才重做受影响证据。
- 核对实际字体、HDR到SDR映射、画幅及字幕安全区；以本次输出为准，不把工具自带英文样式或历史样片作为固定视觉方案。
