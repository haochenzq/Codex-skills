# 声音选择与调用

已有合适声音可直接剪辑，不强制云生成。选型与默认调用许可统一见[公共运行规则](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md)。

| 需求 | 默认入口 |
| --- | --- |
| 按确定文案生成旁白或台词 | 原生豆包TTS2.0，任务类型`tts` |
| 按描述生成BGM、环境声、音效 | 原生Seed-Audio1.0，任务类型`audio`；MediaKit代理按需选用 |
| 编排、剪辑和混音 | 本地Remotion/video-use/FFmpeg |

## 共用执行入口

原生请求JSON与任务放本次制作过程目录，结束后按公共收尾规则处理；`prepare`仅本地准备，依据公共默认许可直接提交一次：

```powershell
$taskSpeechPython = 'C:\Users\lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskSpeechEntry = 'C:\Users\lenovo\.codex\runtimes\personal-video\run_api.py'
& $taskSpeechPython -B -X utf8 $taskSpeechEntry production_cloud prepare '<tts或audio>' '<请求JSON绝对路径>' '<本项目新任务目录>'
& $taskSpeechPython -B -X utf8 $taskSpeechEntry production_cloud submit '<任务目录>' --allow-paid-calls
& $taskSpeechPython -B -X utf8 $taskSpeechEntry production_cloud status '<任务目录>'
```

`completed`后使用本地音频；HTTP200不算完成。两类入口均复用既有豆包语音Key，未知提交保留请求ID/Logid，不重提、不改走另一收费路径。运行期间响应、用量和输出放在任务内，base64、凭据和临时签名URL不回传聊天。

## 旁白与角色配音

```json
{
  "req_params": {
    "text": "替换为本片台词",
    "speaker": "zh_female_vv_uranus_bigtts",
    "audio_params": {"format": "mp3", "sample_rate": 24000, "enable_subtitle": true}
  }
}
```

入口为`/api/v3/tts/unidirectional`。当前适配器接收1–300字符、显式音色和MP3；长文/多角色按句段组织，不静默截断。语气、语速和音色按作品及当前文档选择。完成后读取`speech.mp3`与`transcript.json`；字级字幕用`enable_subtitle`并检查`timestamp_status=available`，不用旧`enable_timestamp`，缺字幕不自动重新配音。TTS不执行query/download。

## BGM、环境声与音效

```json
{
  "model": "seed-audio-1.0",
  "text_prompt": "描述本片用途、期望时长、节奏、乐器或声源、情绪及是否有人声",
  "audio_config": {"format": "wav", "sample_rate": 48000},
  "watermark": {"aigc_watermark": false, "aigc_metadata": {"enable": false}}
}
```

入口为同步`/api/v3/tts/create`，不虚构可查询的云任务ID。当前适配器支持纯提示词、WAV/MP3；参考音频/图片上传未接入。官方提示词≤3000字符、单次最长120秒，提示中的时长不保证精确输出，计费按`original_duration`。

输出为`generated.wav/mp3`，通过格式、时长、完整解码及有效信号检查才标完成。`result_received`保留已收音频，可用`production_cloud download '<任务目录>'`恢复同一结果而不生成；`submission_unknown`停止待核对。复用程序已有检查结果；内容仅按公共规则检查本次改动或明确异常，不默认另行全段试听。需要分别调整的音乐、人声、音效分轨组织；混合生成不视为可拆分音轨。首版时间轴仅支持音乐和一路旁白，复杂混音按需用其他本地入口。

MediaKit代理适合明确需要异步ID、查询、回调或已授权备用的流程：`mediakit_submit_task`设`tool=call-maas-proxy`、`api=doubao.audio_generation`，原生请求置于`maas_params`。须完成MediaKit→SA授权；保存task_id并查询同一任务，只有`body.status=completed`后读取`body.result.maas_result`、落盘及验收，受理不算成功。不因直连状态未知重复生成。

模型目录区分研究、接入和实测，短样本不代表全场景。官方依据：[TTS](https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http?lang=zh)、[音频生成直连](https://docs.volcengine.com/docs/DoubaoVoice/audio-generation-http?lang=zh)、[可选代理](https://docs.volcengine.com/docs/Intelligentprocessing/audio-generation?lang=zh)。
