---
name: video-directing-production
description: 用于分集短剧的分镜、画面与人物表演对齐、重拍及参考素材准备，并将确认的镜头整理为 Seedance 提示词和 LibTV 草卡。
---

# 视频导演与制作

先定位用户指定的剧本、分镜和已确认素材。续写或重拍时，用已采用片段的时间码标出衔接位置与需要保留的表演。按当前任务选择下列参考。

- 画面、人物表演与重拍需求对齐：[画面描述](references/directing.md)。
- 人物、场景、道具、白模、声音或续写源：[参考素材](references/references.md)。
- 提示词定稿、LibTV 草卡与回读：[生成与建卡](references/production.md)。

画面设计与参考素材清单可独立交付。定稿 Seedance 提示词使用已安装的 sd25-pe；保存草卡需要可用的 LibTV 插件或已登录的网页。缺少对应工具时，交付已确认的镜头说明、参数和素材挂载清单，说明剩余步骤。

三维预演可调用 blender-local，分析素材可调用 volc-video-analysis，明确切点的剪辑可调用 video-use。用户明确指定火山直连生成时，交由 volc-video-generation 按其流程处理。
