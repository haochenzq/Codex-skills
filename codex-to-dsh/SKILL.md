---
name: codex-to-dsh
description: 在 Windows 的普通 Codex 主聊天中，按用户提供的 DSH 会话 ID 建立实时文字通话。适用于联系指定的 DeepSeek Harness 会话、双方分工开发和主动回报进展。共享文件时传本机绝对路径。
---

# 与指定的 DSH 会话通话

需要本机 DSH Desktop 已加载 DSH Codex Bridge 0.7.0，Codex 已启用插件配套的轮次钩子，并可使用 Node REPL。用户粘贴完整的 `session-…` ID 并要求联系时，由当前主聊天发起配对。

## 接通

按[接通当前轮的推送](references/push.md)启动后台订阅。收到 `paired` 后核对会话 ID 和插件版本，再报告已接通。同一通话沿用这一条连接。来信由订阅直接推入当前轮次，通知完成后才向 DSH 确认收件。一个 DSH 会话同时连接一个 Codex 主聊天。

## 交谈

用 PowerShell 在同一个 Codex 主聊天发件。每次新发送生成一个请求 ID。

```powershell
$bridge = Join-Path $env:LOCALAPPDATA 'DSH Codex Bridge/packages/0.7.0/client.js'
$sid = '用户给出的完整会话 ID'
$body = @'
请查看 D:\项目资料\工作说明.md，核对后直接告诉我结果。
'@
node $bridge send $sid ([guid]::NewGuid().ToString()) $body
```

联合开发时，第一条消息写清目标、双方分工和验收条件。DSH 用 `reply_to_codex(message)` 主动同步进展、问题或结果。收到来信后按用户授权推进，必要时直接回话。文字、图片或其他文件都可以通过正文中的本机绝对路径交给对方读取。

## 核对结果

Codex 发件的 `accepted` 表示 DSH 已接受输入。DSH 窗口是完整的通话记录：Codex 来信显示为原生聊天消息，DSH 发件卡片保留正文、换行和实际回执。主动推送完成后卡片显示“Codex 已接收”。

连接随原轮次结束。若工具意外中断或连接关闭，向用户报告实际状态。需要继续时，在新的活动轮次用同一 DSH 会话 ID 再配对。断线后消息不会排队补发；结果不明时先核对 DSH 窗口里的记录，避免重复提交。
