---
name: manim-video
description: 使用Manim制作数学、公式推导、算法、数据与技术概念动画，或修改现有Manim场景。普通图文视频、静态图表与无精确图形需求的剪辑不默认选择Manim。
metadata:
  version: '1.0.0'
---

# Manim 动画

本技能是video-use附带的Manim技术入口。整片表达与制作方案按当前任务及项目规则确定，已确认的方案或局部修改不重新访谈；不固定叙事结构、目录、配色、时长或预览轮次。

## 运行与按需参考

使用[共享运行入口](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md)的`run_manim.py <Manim参数>`或`video-tools.ps1 manim <Manim参数>`。首次使用、依赖变化或报错时以Codex自带Python运行[scripts/check_runtime.py](scripts/check_runtime.py)，同一任务复用已验证环境。已有共享Manim、LaTeX、dvisvgm与FFmpeg；实际可用性以检查结果为准，不重复运行上游setup.sh或在作品目录安装依赖。

脚本、配置、`--media_dir`和输出使用当前作品目录绝对路径，按已有结构组织；简单场景无需另建plan.md、拼接清单或声音步骤。中文Text使用实际存在的字体；公式通过共享入口处理中文路径，不手工改全局TeX环境。

| 本次需要 | 读取参考 |
| --- | --- |
| 场景构思与表达 | [场景规划](references/scene-planning.md)、[动画设计](references/animation-design-thinking.md) |
| 对象与动画接口 | [对象](references/mobjects.md)、[动画](references/animations.md) |
| 公式推导 | [公式](references/equations.md) |
| 算法、坐标与数据 | [图表与数据](references/graphs-and-data.md) |
| 镜头和三维 | [镜头与三维](references/camera-and-3d.md) |
| 连续更新和跟踪 | [updater与tracker](references/updaters-and-trackers.md) |
| 样式、标注与版面 | [视觉设计](references/visual-design.md)、[标注](references/decorations.md) |
| 论文讲解 | [论文说明](references/paper-explainer.md) |
| 渲染、编码或报错 | [渲染](references/rendering.md)、[排错](references/troubleshooting.md) |

参考中的配色、节奏、结构和第三方服务均是示例，按当前需求选用；不据此强制固定流程、连接ElevenLabs或新增云调用。需要声音时复用已授权音频，或按公共规则使用既有豆包路线。

## 制作与验证

- 先确定需呈现的关系和变化，再选择适用对象及变换；图形先行、逐项出现和固定透明度仅在有助于本次表达时采用。停顿依阅读与叙事需要安排，不给每个动画机械追加相同时长。
- 复杂或不确定片段按需低清预览；简单修改可直接渲染目标规格，不要求每次先低清再高清。分辨率、帧率、比例及透明通道按项目和本次交付需求设置。
- 核对公式对应、标注位置、运动连续性和阅读时间；多个场景保持适合本片的视觉一致性。技术参数通过不等于内容正确或用户认可。
- 按[一次必要检查](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md#一次必要交付检查)复用程序结果，仅查本次改动或明确异常；素材与源码按项目用途留存。按需参考[质量方法](references/production-quality.md)解决具体布局问题，不执行整套检查清单。
