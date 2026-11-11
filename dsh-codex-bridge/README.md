# DSH 和 Codex 双向聊天

Windows 上的本机桥接。两边每次选择一个已有会话。消息出现在目标会话的原生聊天里，来源显示为「【Codex】」或「【DSH】」。

## 使用

- Codex → DSH。在 Codex 告知 DSH 对话标题或会话 ID。标题同名时按工作区核对。文字、图片和普通文件通过 DSH 原生即时发送模式交给目标会话。
- DSH → Codex。回复本轮唯一获授权的来源会话时，纯文字用 `reply_to_codex`，只传正文。发送真实附件或使用用户本轮指定的既有目标时，用 `send_to_codex`。附件必须来自本会话且已获授权，填写真实的附件 ID 与序号。

双方对话即时发送。空闲会话开启新一轮，活跃会话在当前轮接收输入，可能影响正在进行的工作。桌面端已持有的 Codex 会话由桌面端直接接收，未加载的会话先恢复，再发送。Codex 回执 `sent` 包含消息 ID 和轮次 ID，表示接受了本次输入。实际处理情况以接收会话为准。

### DSH 回传的载荷

| 载荷 | Codex 接收方式 |
| --- | --- |
| 纯文字 | 原生文字输入 |
| 普通文件 | 原生文字输入，附上已校验的 DSH 本机原文件路径及 SHA-256 |
| 原生图片 | 原生图片输入 |

连接 Codex 本机服务失败且尚未提交时，自动启动服务并重连一次。附件无效则报告错误。回执不明时先查目标会话，避免重复发送。

共同任务开始时约定目标、范围、分工和验收。双方在有可核对的阶段结果、下一步或真正的阻塞时主动联系。Codex 可在运行期间直接回读 DSH 原会话并继续推进。达到验收条件后停止发送，单纯的收件确认不产生新任务。

## 安装

在 Windows 上使用已安装的 DeepSeek Harness Desktop、Codex Desktop 和 Node.js 24。在仓库根目录运行以下命令，将桥接源码安装到技能使用的路径。

~~~powershell
$source = (Resolve-Path -LiteralPath '.\dsh-codex-bridge').Path
$packages = Join-Path $env:LOCALAPPDATA 'DSH Codex Bridge\packages'
$package = Join-Path $packages '0.6.6'
if (Test-Path -LiteralPath $package) { throw "目标版本目录已存在，请先核对其来源。" }
New-Item -ItemType Directory -Path $packages -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $package -Recurse
$dsh = Join-Path $env:LOCALAPPDATA 'Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd'
& $dsh plugin --profile desktop add "link:$package" --offline --ignore-scripts
~~~

重新打开 DSH Desktop 并确认「Codex 会话协作」已启用。安装 [codex-to-dsh 技能](../codex-to-dsh/SKILL.md) 后，按技能说明选择目标会话并使用本机客户端。

## 验证

在此目录运行 `node --test` 可执行自动测试。0.6.6 在 Codex 桌面会话活跃时直接向当前轮次发送。只有桌面端明确提示原轮已结束时，才开启新轮。已验证纯文字回传只到达一次、原轮结束后可继续发送，以及活跃轮次接收原生图片。
