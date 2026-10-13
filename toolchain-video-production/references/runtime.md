# 工具链与独立语音入口

公共运行目录：`C:/Users/lenovo/.codex/runtimes/personal-video`。构建项目维护源码与依赖，制作项目保存自己的素材、EDL、时间轴、源码和成片。共享环境只提供运行能力；本路径使用所需制作、合成和独立语音/分析入口，全程排除Seedance。

## 本地制作

```powershell
$taskVideoTools = 'C:\Users\lenovo\.codex\runtimes\personal-video\video-toolchain\video-tools.ps1'
& $taskVideoTools doctor
# 仅选择共享Remotion工程时查询；其余命令按本次路径使用，不逐项执行整段示例。
& $taskVideoTools compositions
& $taskVideoTools production '<本项目timeline.json绝对路径>' --validate
& $taskVideoTools production '<同一timeline.json绝对路径>' '<本项目新版成片绝对路径.mp4>'
# 精确参数按工具帮助与所选专业技能读取
& $taskVideoTools remotion-render --help
& $taskVideoTools video-use --help
```

`--validate`只验证本地素材与区间，不替代渲染。使用首版运行器先读 [timeline.md](timeline.md)。选择独立Remotion工程时核实该工程入口；公共注册器保留已有Composition，作品工程不长期混入公共源目录。使用已安装的本地CLI，不通过临时npx隐式安装。

简单明确的编辑直接制作正式版本；高成本动画或效果不确定时，按需选择少量关键帧或代表性短片验证所需效果。复用`video-use <EDL> <预览输出> --draft`或所选工具已支持的短段/静帧输出；统一`production`入口目前仅接受时间轴、正式输出及`--validate`，没有`--draft/--preview`。预览不是固定步骤，已覆盖的本地制作授权不另设审批；不为制作预览新增云调用或扩展运行器。

需要剪辑方法时读取全局 `C:/Users/lenovo/.codex/skills/video-use/SKILL.md`；本机全局入口及本任务约束优先于上游失效路径或默认ElevenLabs示例。只读取所需Remotion/动画专业技能，不把其示例工具组合强加给作品。

## 独立配音

```powershell
$taskSpeechPython = 'C:\Users\lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskSpeechEntry = 'C:\Users\lenovo\.codex\runtimes\personal-video\run_api.py'
& $taskSpeechPython -B -X utf8 $taskSpeechEntry production_cloud prepare tts '<豆包语音请求JSON绝对路径>' '<本项目新语音任务目录>'
& $taskSpeechPython -B -X utf8 $taskSpeechEntry production_cloud status '<语音任务目录>'
# 本次语音服务、上传和费用已获授权后提交
& $taskSpeechPython -B -X utf8 $taskSpeechEntry production_cloud submit '<语音任务目录>' --allow-paid-calls
```

该段仅使用豆包语音2.0 TTS。需要中英文字级时间戳时显式设置`req_params.audio_params.enable_subtitle=true`，不用旧`enable_timestamp`；完成后检查`timestamp_status=available`及`transcript.json`，`missing/not_requested`不能称字幕已齐，不能自动重新配音。语气指令、语速等按原生请求传入。TTS不执行视频query/download。当前入口有1–300字符范围，长文本先适配，不能静默截断。需要ASR或已有素材分析时按 `volc-video-analysis` 调用，复用有效转写。

## 依赖与恢复

依赖位置、版本与渲染浏览器统一读取[公共运行说明](C:/Users/lenovo/.codex/runtimes/personal-video/RUNTIME.md)；Remotion实际使用共享Chrome Headless Shell。进入新的执行环境或首次实际使用所选能力时核对所需依赖；同一任务已核对的能力在环境变化或报错时再检查，局部改版不重复检查整套环境。`doctor`可用于共享环境核对；Manim入口为 `video-tools.ps1 manim <原生参数>`，其他三维工具按需核实。Studio只是临时服务。

私有凭据由既有独立语音/分析适配器读取，不复制Key、连接配置、签名URL或完整云响应到通用交接包。本次制作保留素材、实际源码、版本与恢复记录；依赖缺失先定位维护项目，避免另建工具或凭据副本。
