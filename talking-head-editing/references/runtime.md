# 统一入口与恢复

统一入口复用已安装的 `volc-video-analysis`、video-use原版helpers及用户级共享运行器；未增加云服务、依赖或凭据配置。素材路径和作品目录以当次任务为准。

## 本机调用

解释器：`C:/Users/lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`。
入口：`C:/Users/lenovo/.codex/skills/talking-head-editing/scripts/talking_head.py`。
共用运行器：`C:/Users/lenovo/.codex/runtimes/personal-video`。

下列PowerShell示例使用作品局部变量；路径只是示例，必须替换为实际素材与工程。

```powershell
$talkPython = 'C:/Users/lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$talkEntry = 'C:/Users/lenovo/.codex/skills/talking-head-editing/scripts/talking_head.py'
$talkEdit = 'D:/作品/口播01/剪辑'
& $talkPython -B -X utf8 $talkEntry prepare $talkEdit 'D:/素材/口播01.mp4' --asr-backend doubao_turbo
& $talkPython -B -X utf8 $talkEntry status $talkEdit
# 本次上传与费用授权覆盖后才执行；一次只推进一个阶段。
& $talkPython -B -X utf8 $talkEntry advance $talkEdit --allow-paid-calls
# completed后自动sync，也可再次本地同步。
& $talkPython -B -X utf8 $talkEntry sync $talkEdit
& $talkPython -B -X utf8 $talkEntry plan $talkEdit "$talkEdit/保留方案.json"
& $talkPython -B -X utf8 $talkEntry render $talkEdit "$talkEdit/口播-v1.mp4"
```

只有 `advance --allow-paid-calls` 能上传或访问云服务。无该标志会返回授权提醒；`status`、`sync`、`plan`、`render` 不联网。用户已有上传/费用授权时直接沿用，无需因为示例注释再确认。

## 模式与复用

- `prepare` 默认 `--mode video_analysis --profile standard --clip-seconds 120 --visual-fps 1 --asr-backend doubao_turbo`，对应豆包录音文件识别1.0极速版；需要标准附加能力时显式选`--asr-backend doubao2`，对应2.0标准版。按公共运行规则核对可用额度和费用授权。豆包ASR用WAV直传；新standard任务返回`visual_transport=ark_file_av`，Lite经Ark Files同时理解画面和真实音轨。两版均保留词时间戳；旧job保留原路线，接续或复用旧缓存时显式指定其原ASR后端，不因新默认值重建或改标。
- `--mode audio_transcription` 只转写；`--mode cuts_only` 只探测本地素材，不建立云job，适用于已指定切点且无需语义判断的编辑。无转写模式不会凭空生成字幕。
- `import-job <edit_dir> <job_id>` 导入已完成、同原片SHA256的豆包2.0或极速版任务，复用原词时间戳，0云调用。画面分析是否完成由实际任务决定，不能将纯转写冒充全模态分析。
- `prepare ... --reuse-asr-job <job_id>` 复用完成的ASR到新的画面分析任务：必须匹配原片SHA256、分段起点/时长和音频SHA256。复用时选择缓存的同一ASR后端，保留真实来源，不改标2.0/极速版；仅修改新job，原结果不动；不匹配则停止，不偷偷重识别。同目录重复prepare会返回已准备job，不重复创建。
- `--profile deep/fast` 对应Seed Pro/Turbo纯画面路线，不承担完整音频理解；需要语气、音乐、环境声或视听关系时用standard/Lite。不要把语音极速版与Seed Turbo混为一谈。
- 需要标准ASR标签/测量时用`--asr-backend doubao2 --asr-feature emotion --asr-feature speech_rate --asr-feature volume`，只开启任务需要的项；多人可加`--speaker-info`。检查`asr_feature_coverage`，缺失不是成功；标签不替代Lite的音乐、环境声和视听关系理解。兼容转写保留分句`additions`。旧缓存没有请求所需能力时停止复用，不重标或自动重识别。
- `sync/status`按素材返回`audio_understanding`；完整视听证据保存在`analysis/video_analysis.json`，不能只看`visual_analysis_completed`。

`render <edit_dir> <output> --preview`使用现有低清本地预览。争议选段或接缝短片通过现有本地工具按需提取；不新增云分析、不覆盖正式版本，也不把短片提取当作新的入口子命令。验收结论由Codex写入作品现有记录，绑定具体输出版本；入口没有自动听审或自动判定成片通过的能力。

## 文件与版本

作品目录保存 `talking-head.json`、`takes_packed.md`、兼容video-use的 `transcripts/<素材编号>.json`、必要的 `analysis/video_analysis.json`、`editing-plan.json`、`edl.json`、`master.srt`和用于烧录的 `master.ass`。兼容JSON含顶层 `words`、`type=word`、原词时间和连续中文显示文字；原始转写路径与SHA256保留。

云job由既有运行器保存在其 `api/outputs/<job_id>`；旧job仍按既有legacy兼容读取。作品保存指针和证据，不搬移云状态或凭据。每个渲染版本的中间文件在 `render-work/<输出文件名>/`，已有版本不能覆盖；失败后先读日志、保留恢复资料，再使用新版本名重做本地渲染。

素材内容变化使旧结果失效，不能复用。工具生成的字幕/EDL被独立改动时停止覆盖；在新方案里记录修改或保留另一个版本再重建。不要批量删除锁或临时文件。

统一入口是已部署适配器的调用层，未修改上游helpers和共享运行目录；中文字幕样式通过新技能内的本地合成适配读取。维护安装与历史验收位置见构建相关项目入口，不依赖维护源码运行。
