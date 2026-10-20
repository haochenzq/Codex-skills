# 本机运行依赖

本Skill供当前Windows用户跨项目复用。运行代码、Python依赖、媒体工具已部署到用户级 `C:/Users/lenovo/.codex/runtimes/personal-video`。构建项目保留维护源码、必要测试代码及在用部署资料，验收过程材料按项目规则清理；运行入口不再导入构建项目代码。依赖、凭据位置及模型/费用规则统一读取[全局运行说明](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md)，本文件只补分析入口与参数用法。

## 入口与工具

- 用户级注册：`C:/Users/lenovo/.codex/config.toml`中的`mcp_servers.volcengine_api`和`mcp_servers.volcengine_mediakit`。
- 解释器：`C:/Users/lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`。
- 启动器为上述全局目录的 `run_api.py`，参数分别是 `server` 与 `mediakit_server`；适配器在 `api/`，FFmpeg在 `native/ffmpeg/`，Python依赖在 `python-packages/`。
- 主要工具：`volc_prepare_workflow`、`volc_advance_workflow`、`volc_workflow_result`；模型比较用`volc_model_catalog`，鉴权异常才用`volc_connection_status`。豆包ASR直接提交已有音频；MediaKit按需做独立字幕OCR、提取音频、云转码或恢复旧任务，普通分析不重复上传/提交。具体选择理由见公共运行说明。

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

此例适用于普通字幕/单人素材比较；需要标准附加能力或超出极速限制时显式改为`asr_backend="doubao2"`，按公共规则选择适配后端并直接使用默认调用许可。共享API的默认值仍是2.0，已有job或缓存保持真实后端。路径只是示例，必须替换为用户实际选定的文件。新任务状态目录、跨聊天接续和旧任务读取方式以全局运行说明为准；返回的产物绝对路径是交付依据。用户需要的报告按当前授权交付；处理中不移走状态或依赖，结束后按公共收尾规则处理独立job与中间结果。

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
