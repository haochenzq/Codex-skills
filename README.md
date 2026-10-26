# Codex skills

个人 Codex 技能集合，收录当前使用的 7 个个人技能。同步日期：2026-10-26。

## 技能导航

| 技能 | 用途 |
| --- | --- |
| [blender-local](blender-local/SKILL.md) | 本地 Blender 建模、材质、灯光、动画及 GLB 导出 |
| [threejs-local](threejs-local/SKILL.md) | 本地 Three.js 实时 3D 开发、预览和交互验证 |
| [social-video-download](social-video-download/SKILL.md) | 抖音分享视频下载 |
| [talking-head-editing](talking-head-editing/SKILL.md) | 口播语义选段、字幕、剪辑与交付 |
| [video-use](video-use/SKILL.md) | 明确操作的剪切、字幕、调色、混音和叠加 |
| [volc-video-analysis](volc-video-analysis/SKILL.md) | 视频分析、音频转写、比较及任务恢复 |
| [volc-video-generation](volc-video-generation/SKILL.md) | 火山 Seedance 视频生成、原任务查询和下载 |

适用范围、依赖、执行流程及授权要求以各技能的 `SKILL.md` 为准。系统技能和第三方插件技能由各自发布方维护，不收录在本仓库。

## 源码与使用

维护源码位于本机构建项目的各模块 `skill-package/<技能名>/`，全局安装在 `C:/Users/lenovo/.codex/skills/`。本次以维护源码覆盖仓库中的对应技能目录，28 个技能文件已核对与全局安装副本一致，7 个技能格式校验通过。

仓库保留本机运行路径；克隆或复制技能不等于完成部署。在其他电脑使用前，需要按技能说明配置解释器、FFmpeg、Blender、Node、MCP 连接及相应共享运行环境。Three.js 模板自带依赖清单和锁文件；视频技能使用说明中指定的宿主运行入口。

不上传账号凭据、Cookie、用户媒体、真实任务回执、缓存、虚拟环境或第三方依赖目录。保留随技能提供的许可证。

## 历史配套

- [video-runtime](video-runtime/README.md) 是此前保留的局部运行源码，未随本次技能同步更新，不代表当前宿主部署或完整运行环境。
- [chat-with-codex 归档](archives/chat-with-codex/README.md) 是已卸载实验方案的历史资料，不是当前技能。

本次已从当前分支移除停用的 `libtv-drama-production`、`seedance-video-production`、`toolchain-video-production`、`video-cover`、`workspace-maintenance`，以及旧 `video-use` 内嵌的 `manim-video` 技能和过时配套；旧版本可通过 Git 提交历史恢复。

本次验证仅涉及技能格式、Python 语法、文件一致性及上传内容检查，未调用收费接口或重新执行媒体制作任务。
