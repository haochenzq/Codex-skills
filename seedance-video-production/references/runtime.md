# Seedance 运行入口

维护源码在构建相关项目；运行代码与依赖在 `C:/Users/lenovo/.codex/runtimes/personal-video`。缺失时先定位维护入口，不复制另一套运行器或凭据。任务与输出保存到当前制作项目。

## 视频任务

```powershell
$taskCloudPython = 'C:\Users\lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskCloudEntry = 'C:\Users\lenovo\.codex\runtimes\personal-video\run_api.py'
& $taskCloudPython -B -X utf8 $taskCloudEntry production_cloud prepare video '<请求JSON绝对路径>' '<制作项目中新任务目录>'
& $taskCloudPython -B -X utf8 $taskCloudEntry production_cloud status '<任务目录>'
# 本次方案、型号、上传和费用已获授权后提交
& $taskCloudPython -B -X utf8 $taskCloudEntry production_cloud submit '<任务目录>' --allow-paid-calls
& $taskCloudPython -B -X utf8 $taskCloudEntry production_cloud query '<视频任务目录>'
& $taskCloudPython -B -X utf8 $taskCloudEntry production_cloud download '<成功的视频任务目录>'
```

`prepare`只本地准备，已有目录拒绝覆盖。提交未知或处理中继续查询原任务；不为绕过状态新建任务。成功下载后直接交付原片，具体边界见 `SKILL.md`。

CLI的query/download需要本地任务目录，不能把云任务ID直接当作目录。仅收到云任务ID时，先在当前制作项目的请求/状态记录中定位原目录；找不到时说明恢复资料缺口，索取最小必要的任务目录或记录。不得重新prepare/submit代替恢复查询。

用户级 `volcengine_api` MCP也提供prepare/status/submit/query/download工具，按实际schema调用并复用同一job_id；其默认任务目录在公共运行目录 `api/outputs/production/`。需要制作项目独立保存时优先使用上述CLI。桌面连接未刷新时可用CLI，不建立另一套MCP。

## 独立语音与参考

TTS使用同一CLI，把 `prepare video` 改成 `prepare tts`；请求与授权按豆包语音2.0实际需求处理。中英文字幕需要`req_params.audio_params.enable_subtitle=true`，并核对`timestamp_status=available`，不能把音频完成当时间戳齐全。TTS成功后不执行视频query/download。ASR与参考片分析使用 `volc-video-analysis`，不自动分析生成原片。

确需本地预演时，可调用公共 `video-toolchain/video-tools.ps1` 的doctor、Remotion或video-use入口，并读取相应专业技能；这些调用只准备参考。公共依赖由构建项目维护，作品源码和素材保留在制作项目。

## 凭据与当前依据

适配器从用户现有私有文件读取凭据。说明、交接包及一般输出不包含Key、连接配置、签名URL或完整云响应；任务内部响应按私有恢复资料处理。程序收费开关不能代替用户授权。

具体生成前查[创建视频任务](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)、[方舟价格](https://docs.volcengine.com/docs/ark/model-pricing?lang=zh)及所选型号提示词/参考指南。独立语音查[豆包TTS接口](https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http?lang=zh)。历史模型清单仅作候选索引，不当作当前开通或额度保证。
