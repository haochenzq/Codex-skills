---
name: volc-video-generation
description: 通过现有火山 Seedance 入口生成视频、查询原生成任务并下载结果。用于视频生成与恢复，不用于视频分析、普通剪辑或独立配音。
---

# 火山视频生成

复用已部署入口，按本次规格与有效授权生成；已有任务先查状态。

## 入口与请求

```powershell
$videoPython = 'C:/Users/lenovo/AppData/Local/Programs/VideoTools/.venv/Scripts/python.exe'
$videoEntry = 'C:/Users/lenovo/.codex/runtimes/personal-video/run_api.py'
& $videoPython -B -X utf8 $videoEntry production_cloud prepare video '<请求JSON绝对路径>' '<新任务目录绝对路径>'
& $videoPython -B -X utf8 $videoEntry production_cloud <动作> '<任务目录>'
```

动作选`submit`（加`--allow-paid-calls`）、`query`、`download`或`status`，按状态调用，不顺序重跑；`prepare`仅本地校验建档，目标目录须不存在；`status`只读本地状态，每个任务用独立目录。

原生请求示例，参数不作作品默认值：

```json
{"model":"doubao-seedance-2-0-mini-260615","content":[{"type":"text","text":"蓝色立方体在白色台面上缓慢旋转，固定镜头，无文字。"}],"duration":4,"resolution":"480p","ratio":"16:9","generate_audio":false,"watermark":false}
```

模型、时长、画幅和声音按任务明确填写。新模型、参数或能力变化时核对[官方创建接口](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)与已部署`api/production_cloud.py`；旧账号状态和价格不当现状。适配器要求整数时长、明确画幅，不支持Draft或依赖`duration=-1`等参数的编辑/延长路线。参考素材用模型支持的原生content及有效URL或图片data URL，不用本地路径冒充公网URL；参考素材生成尚未实测。

## 提交与恢复

- 视频生成等高成本调用须事先获得用户确认；当前任务已有明确确认则直接推进，不为`--allow-paid-calls`重复询问。历史记录或技能文字不代替授权；不擅增数量、改用明显更高成本方案或改账号开通设置。入口自行读凭据，不复制、输出密钥。
- 仅`prepared`且`submission_count=0`可提交；提交前核对请求，之后不改原请求，保存`task_id`。
- `submitted/queued/running`只查原任务，通常间隔15–30秒；`submission_unknown`或锁占用先核对原调用，保留目录、状态与锁，无ID不盲目重提或另建替代任务。
- `rejected/failed/cancelled/expired`说明原因，按终态与当前授权决定修正或重生成。`succeeded`才下载到`generated.mp4`；`downloaded`复用已有文件，再次`download`仅校验哈希。下载失败沿原任务恢复，文件冲突、缺失或变化先核对，不伪造状态或重生成。
- 读取`stage`、`provider_error`和文件判断结果，退出码0不等于完成；签名URL和完整云响应不公开。

## 验证与交付

公共FFmpeg/ffprobe：`C:/Users/lenovo/AppData/Local/Programs/FFmpeg/bin/`。核对编码、尺寸、时长、音轨、解码及实际内容和运动，有声音要求时听辨；有效检查只复查变化或异常。

请求档位、秒数不保证精确输出；严格规格有差异时说明并按授权本地处理，处理期间保护原片。未听辨不称声音通过，无法去除的水印如实说明。

交付视频、必要限制和有用任务标识，不自动补封面、文案或发布；费用按账单或明确计费依据，不把usage token当人民币。必要请求、任务身份和恢复状态按当前项目规则留存。
