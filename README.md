# Codex skills

个人 Codex 技能集合。仓库地址：[haochenzq/Codex-skills](https://github.com/haochenzq/Codex-skills)。

本次同步日期：2026-10-21。由原 `haochenzq/test` 仓库更名，沿用原有 Git 提交历史。收录 9 个顶层个人技能及 1 个内嵌 Manim 技能，不包含 Codex 系统技能或第三方插件技能。

## 技能导航

| 技能 | 用途 |
| --- | --- |
| [libtv-drama-production](libtv-drama-production/SKILL.md) | LibTV 短片制作、修改、恢复及角色资产 |
| [seedance-video-production](seedance-video-production/SKILL.md) | Seedance 直连生成与原片交付 |
| [social-video-download](social-video-download/SKILL.md) | 抖音分享视频下载 |
| [talking-head-editing](talking-head-editing/SKILL.md) | 口播语义分析、删留与剪辑 |
| [toolchain-video-production](toolchain-video-production/SKILL.md) | 本地整片创作、动画及复杂合成 |
| [video-cover](video-cover/SKILL.md) | 视频及合集封面设计 |
| [video-use](video-use/SKILL.md) | 明确切点的剪切、字幕、调色及叠加 |
| [manim-video](video-use/skills/manim-video/SKILL.md) | 数学、公式、算法与技术概念动画 |
| [volc-video-analysis](volc-video-analysis/SKILL.md) | 现有视频分析与音频转写 |
| [workspace-maintenance](workspace-maintenance/SKILL.md) | 项目规则、技能规范与资料维护 |

各技能的适用范围、参考文档及执行约束以对应 `SKILL.md` 和其链接为准。保留上游说明和许可证；`video-use` 中的上游安装说明不覆盖个人技能当前运行入口。

## 源码与同步

个人维护源码位于本机 `D:/Codex项目文件夹/构建相关/技能与插件/`，分别归属 LibTV漫剧工作流、火山API接入、视频下载技能、视频封面、资料维护技能及个人技能运行环境。全局安装副本位于 `C:/Users/lenovo/.codex/skills/`。

本次已逐文件核对个人维护源码与安装副本一致；`video-use` 的 helpers、参考资料及内嵌 Manim 的上游配套从现用安装包补齐。仓库保存技能正文、脚本、参考资料、必要静态资源和已有配套测试。

## 使用前提

这是个人技能源码集合，保留本机路径及项目范围约束。复制到其他电脑后，需要配置相应项目路径、解释器、服务连接及运行环境；仅克隆仓库不等于完成部署。

- 下载技能依赖见[下载说明](social-video-download/README.md)和[依赖清单](social-video-download/runtime/manifest.json)。
- 视频技能所需的共享运行环境见各技能的 runtime 参考；仓库既有的[运行代码](video-runtime/README.md)仅包含局部源码，不是完整运行环境。
- 不上传账号凭据、Cookie、真实任务回执、用户媒体、缓存，以及 FFmpeg、浏览器、Python/Node 等第三方依赖目录。

本次同步核验包括 10 个技能入口格式校验和源文件内容一致性核对；未重新运行付费生成、下载或云端分析任务。
