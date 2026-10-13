# 本机运行依赖

本Skill供当前Windows用户跨项目复用。运行代码、Python依赖、媒体工具已部署到用户级 `C:/Users/lenovo/.codex/runtimes/personal-video`。构建项目保留维护源码与验收资料；运行入口不再导入构建项目代码。依赖、凭据位置及模型/费用规则统一读取[全局运行说明](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md)，本文件只补分析入口与参数用法。

## 入口与工具

- 用户级注册：`C:/Users/lenovo/.codex/config.toml`中的`mcp_servers.volcengine_api`和`mcp_servers.volcengine_mediakit`。
- 解释器：`C:/Users/lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`。
- 启动器为上述全局目录的 `run_api.py`，参数分别是 `server` 与 `mediakit_server`；适配器在 `api/`，FFmpeg在 `native/ffmpeg/`，Python依赖在 `python-packages/`。
- 主要工具：`volc_connection_status`、`volc_prepare_workflow`、`volc_advance_workflow`、`volc_workflow_result`；模型选择时用`volc_model_catalog`。独立MediaKit工具用于排查或用户明确要求的独立任务，普通流程不重复上传/提交。

MCP工具名可能带`mcp__volcengine_api__`或`mcp__volcengine_mediakit__`前缀。先使用这些工具，不混用其他`volc_media`服务的任务ID和参数。工具未显示时，确认用户级注册及入口仍存在，再刷新工具或重启Codex；不要自行另写一个云端适配器或把凭据塞进聊天。

新Lite视频任务应返回`visual_transport=ark_file_av`。旧已加载MCP进程可能仍运行旧代码；此时用上述`run_api.py server`启动新鲜stdio会话并调用同名工具，或使用已部署口播CLI的prepare/advance（见口播技能运行说明），不需要用户逐项检查设置。旧job缺少该字段继续原路线；新增视听覆盖须创建新任务，复用经哈希核对的ASR，不能重标旧结果。

`volc_connection_status`和`mediakit_connection_status`只核对本地凭据可读，不验证实时账号权限。无需在每次正常接续时重复探测云端鉴权。

## 参数示例

```json
{
  "paths": ["D:/素材/视频一.mp4", "D:/素材/视频二.mp4"],
  "task": "multi_video_summary",
  "profile": "standard",
  "clip_seconds": 120,
  "fps": 1,
  "max_frames": 120,
  "speaker_info": false,
  "asr_features": [],
  "asr_backend": "doubao_turbo",
  "summary_backend": "local"
}
```

此例适用于普通字幕/单人素材比较；需要标准附加能力或超出极速限制时显式改为`asr_backend="doubao2"`，按公共规则核对额度与费用授权。共享API的默认值仍是2.0，已有job或缓存保持真实后端。路径只是示例，必须替换为用户实际选定的文件。新任务状态目录、跨聊天接续和旧任务读取方式以全局运行说明为准；返回的产物绝对路径是交付依据。复制报告到用户指定位置可按当前授权执行，不移走任务状态或运行依赖。

## 分层读取结果

先调用`volc_workflow_result(job_id, include_evidence=false)`，取得状态、覆盖计数、`folder`、`artifacts`和`local_summary_required`。这只省略整份`evidence`，不删除文件、不改变任务状态，也不会自动完成本地汇总。

再本地解析`folder/video_analysis.json`，先读取每个`videos`条目的`asset_id/name/duration/complete/stage_states/audio_understanding/asr_feature_coverage/summaries`。必须覆盖所有素材和所有分段摘要；概览计数或模型摘要本身不能证明结论准确。随后按目标读取必要字段及关键区间：

| 目标 | 主要证据 |
| --- | --- |
| 内容、论证与原话 | `transcript`，涉及原话的结论核对分句/词时间 |
| 镜头、动作与文字 | `scenes/events/ocr/highlights`，必要时查看关键帧或原片 |
| 语气、音乐与环境声 | `speech_tone/music/sound_events/av_relations`及声音覆盖 |
| 多视频比较 | 每份素材的同一比较维度，关键差异回查原始证据 |

每份素材的JSON位于`folder/<asset_id>/video_analysis.json`；现有字段文件含`transcript.json`、`scenes.json`、`events.json`、`ocr.json`、`highlights.json`及四类视听JSON，按实际生成情况读取。可用本地Python解析大JSON并只输出选定字段/时间区间；过滤是本地读取操作，不向MCP传它不接受的新参数。选择各字段或综合`timeline`中的一种表示，避免重复读同一内容；简单短任务需要全量时可直接用`include_evidence=true`。未读到目标所需证据时补读已有结果，不凭摘要猜测或默认重新调用云分析。

## 配置与凭据

标准2.0需要分句情绪标签、语速或音量时按需填`asr_features=["emotion","speech_rate","volume"]`；选项映射到原生请求，结果保留分句`additions`并提供`asr_feature_coverage`。极速拒绝这些附加选项，不静默忽略或切换后端；`missing/partial`须明确。普通转写保持空列表，音乐、环境声和视听关系仍由Lite负责。

`api/connection.json`位于全局运行目录，仅保存凭据引用；凭据位置以[全局运行说明](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md)和实际配置为准。正常任务不读取密钥文件；只有用户需要凭据或鉴权排查时才核对相关引用，不复制Key到说明或聊天。

语音2.0明确指定`volc.seedasr.auc`，极速版指定`volc.bigasr.auc_turbo`和同步flash接口；两者均使用`request.model_name=bigmodel`。曾用指定方舟通用Key直连语音失败；独立语音Key成功。这是已记录的具体调用结果，不推广为所有火山路径的普遍限制。用户需要凭据/鉴权排查时才读取相应配置，不批量读取其他项目或密钥文件。

## 权威记录与验收范围

- 方案、官方费用依据和当前模型/工作流说明：`D:/Codex项目文件夹/构建相关/02-技能与插件/SK001-火山API接入/接入方案.md`；只读取当前任务所需小节。
- 账号五类45项快照：同目录`模型核对清单.md`、`model_inventory.json`；官方37个方舟版本ID与11项语音产品分别登记。账号状态与公开价格均为2026-10-03快照，重要选型或计费变化需要重新核实。2026-10-11最新账号免费额度和授权证据见同目录`免费额度与授权核对-20261011.md`；运行选择与跨服务检查统一见[公共运行规则](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md)。历史25项检查不包含本次极速版和本地汇总改动，最新范围见`个人技能运行环境/工作流审计-20261011.md`。
- 初版完整云端验收：`outputs/292e57215d0c493e95339e3e8387b723/acceptance.json`，两段自制8秒视频、MediaKit字幕、Seed Lite画面、汇总；6次尝试中1次网络状态未知，经明确授权补做。
- 豆包默认音频分支验收：`outputs/d82fbd1ff3c141f8be534a8ac82aa21f/acceptance.json`，1段8秒自制素材，上传/转码URL/原生2.0/分句与词时间戳/JSON/TXT/SRT通过；恰好1次转码＋1次ASR、无自动重试。
- 本地25项检查覆盖模拟的新多视频流程、毫秒换算与原片偏移、旧任务兼容、超时防重复等。10月11日标准2.0/极速完成84秒同参数口播对比，结果见`火山API接入/ASR对比-20261011/实测报告.md`；复杂长视频、多说话人、Pro/Seed Turbo、其他语音模型仍未完成云端评测；不由这些短素材证明全场景准确率。

上述验收已完成，不再推进。先前逐次收费授权已使用完；Skill只复用实现和方法，不继承新素材的收费额度。

2026-10-11真实音轨已接入：新standard任务将48kHz AAC音轨保留在MP4代理内，经Ark Files使用Lite预处理与同一Lite推理，不再走MediaKit静音视觉Chat。ASR仍用独立16kHz WAV与词时间戳。视听字段与时间偏移合并到原片，见`火山API接入/Lite视听验收-20261011/验收记录.md`；旧任务、纯转写与显式Pro/Turbo视觉路径不静默改写。
