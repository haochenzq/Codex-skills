# 分析运行器修复源码

2026-10-15。本目录保存已发布个人视频共享运行器的局部源码与对应回归测试，供既有部署维护和代码审查；它不是独立安装包，也不包含完整运行器或依赖。

- `adapter.py`：将HTTP成功且ASR供应商状态码为`20000003`的响应识别为明确的`no_speech`，保留原响应和任务标识；HTTP失败不因该码被判成功。
- `workflow.py`：极速同步及标准查询均接受明确无语音终态，保留空转写并继续音乐、OCR与视听分析。未知/超时仍停止防重提；空的普通成功转写不冒充明确无语音。
- `recover_no_speech(job_id, clip_id)`：仅在人工核对既有原回执、任务标识、音频哈希及状态后恢复；独占锁、原任务备份和来源记录保持可追溯。它不发起云请求，也不处理其他失败类型。
- `test_adapter.py`、`test_workflow.py`：原维护工程的完整对应测试文件，包含以上修复的正例、反例和本地幂等恢复检查。

使用方式：先在维护副本保留既有完整运行环境及任务备份，再将两个运行文件分别映射到现有共享环境的`api/adapter.py`与`api/workflow.py`，核对内容后发布。长驻MCP进程需要重新启动才会读取更新；不得复制覆盖连接配置、凭据或outputs任务目录。

测试文件应置于完整API维护源码旁运行：`python -m unittest test_adapter test_workflow -v`。需要既有`catalog`、`speech_catalog`、`mediakit`、MCP服务器及其原依赖，Python 3.11+、`httpx==0.28.1`、`mcp==1.30.0`和FFmpeg/ffprobe；媒体工具由`VOLC_FFMPEG`、`VOLC_FFPROBE`指定。不要直接在含真实凭据或活动任务的运行目录执行测试。维护工程77项模拟服务回归通过（含制作与口播回归），另通过新鲜已部署入口的只读验收；本次修复与恢复未新增云调用。这不等于新的云端全场景验收。

官方状态码依据：[录音识别标准版文档](https://docs.volcengine.com/docs/DoubaoVoice/LargemodelrecordingfilerecognitionstandardversionAPI?lang=zh)。明确无语音不代表没有音乐或环境声，也不代表其他阶段已完成。

本目录不含凭据、机器配置、真实任务标识、原始回执、用户素材或恢复备份。
