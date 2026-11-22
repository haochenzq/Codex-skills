# DSH 和 Codex 双向聊天

Windows 上的本机桥接。DSH 与指定的 Codex 主聊天在后台交换消息和附件，支持普通启动的 Codex 桌面端。

## 使用

- Codex → DSH。在 Codex 告知 DSH 对话标题或会话 ID。标题同名时按工作区核对。文字、图片和普通文件通过 DSH 原生即时发送模式交给目标会话。
- DSH → Codex。纯文字用 `reply_to_codex`，附件用 `send_to_codex`。本轮有唯一授权目标时优先使用该目标，本轮没有目标时使用唯一已配对的 Codex 会话。有多个可选目标时，用 `send_to_codex` 指定其中一个链接或 ID。附件必须来自本 DSH 会话且已获授权，填写真实的附件 ID 和来源序号。

Codex 发给指定 DSH 会话的消息被接受后，桥会保存双方会话的配对。用户也可在 DSH 中明确选择一个 Codex 会话，发送成功后建立配对。配对保存在本机，重启 DSH 后仍可用于主动发送文字和附件。`--reply-to` 指向另一个 Codex 会话时只指定本次回复路径。

Codex 子 Agent 发起协作时，默认回传和新配对指向所属主对话。显式指定子 Agent 时，桥会提示选择主对话。

### 发送到当前轮次

DSH 调用 `send_to_active_codex(target, message)`，把文字交给指定主聊天正在处理的轮次。首次使用按下文配置用户级钩子。现有和新建的普通主聊天均可登记，用户明确指定目标或建立配对后即可定向发送。轮次在工具返回或准备结束时读取消息。登记缺失、轮次已结束或交付超时时，严格发送返回错误。

回执 `hook-delivered` 包含消息 ID 和轮次 ID，表示接收钩子已经输出消息。用接收聊天同一轮的实际回复确认处理结果。普通 `send_to_codex` 也会优先向已登记的活动轮次发文字；其他情况下可以使用桌面直接投递或 Codex 原生队列。`sent` 表示直接输入已被接受，`queued` 表示已入队，入队消息由桌面在聊天空闲时处理。已提交但回执缺失时先核对目标聊天。

### DSH 回传的载荷

| 载荷 | Codex 接收方式 |
| --- | --- |
| 纯文字 | 活动轮次的钩子上下文、原生文字输入或会话队列 |
| 普通文件 | 原生文字输入，附上已校验的 DSH 本机原文件路径及 SHA-256 |
| 原生图片 | 原生图片输入 |

连接 Codex 本机服务失败且尚未提交时，自动启动服务并重连一次。附件无效则报告错误。回执不明时先查目标会话，避免重复发送。

共同任务开始时约定目标、范围、分工和验收。双方在有可核对的阶段结果、下一步或真正的阻塞时主动联系。Codex 可在运行期间直接回读 DSH 原会话并继续推进。达到验收条件后停止发送，单纯的收件确认不产生新任务。

## 安装

在 Windows 上使用 DeepSeek Harness Desktop、Codex Desktop 和 Node.js 24。配套技能从固定的本机目录调用桥接客户端。请在仓库根目录执行。

~~~powershell
$source = (Resolve-Path -LiteralPath '.\dsh-codex-bridge').Path
$packages = Join-Path $env:LOCALAPPDATA 'DSH Codex Bridge\packages'
$package = Join-Path $packages '0.6.8'
New-Item -ItemType Directory -Path $packages -Force | Out-Null
if (Test-Path -LiteralPath $package) {
  $backup = "$package.backup-$([guid]::NewGuid())"
  Copy-Item -LiteralPath $package -Destination $backup -Recurse -ErrorAction Stop
}
New-Item -ItemType Directory -Path $package -Force | Out-Null
Get-ChildItem -LiteralPath $source | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $package -Recurse -Force -ErrorAction Stop
}
$dsh = Join-Path $env:LOCALAPPDATA 'Programs\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd'
& $dsh plugin --profile desktop add "link:$package" --offline --ignore-scripts
if ($LASTEXITCODE -ne 0) { throw 'DSH plugin installation failed.' }
node (Join-Path $package 'configure-hooks.js')
if ($LASTEXITCODE -ne 0) { throw 'Codex hook configuration failed.' }
~~~

同名 0.6.8 目录也需要更新文件。安装步骤先保存原插件副本。钩子脚本只向当前用户的 Codex 配置合并五项命令，修改已有配置时会保存备份。命令固定为执行安装器的 Node 绝对路径。

1. 将 [codex-to-dsh 配套技能](../codex-to-dsh) 目录复制到 `$CODEX_HOME/skills`，默认位置为 `~/.codex/skills`，已有同名技能时先备份本地改动。
2. 在 Codex 的 `/hooks` 原生审阅中核对并信任指向本次安装目录 `turn-channel.js` 的 `UserPromptSubmit`、`PreToolUse`、`PostToolUse`、`Stop`、`Interrupt`。如果此前手动配置过相同项目钩子，备份后从对应项目移除重复的桥接条目。
3. 重启 DSH Desktop，再用普通图标重开 Codex，确认启用了「Codex 会话协作」。从目标 Codex 聊天给 DSH 发一条消息建立配对。

## 验证

在本插件目录运行 `node --test`，可验证会话配对、子 Agent 回传、附件、钩子安装和当轮收件。实际验收时，先记下目标聊天正在进行的轮次 ID，再从 DSH 发送仅导演知道的校验码，并核对接收方在同一轮的回复。
