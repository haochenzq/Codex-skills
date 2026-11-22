# 接通当前轮的推送

在普通主聊天中执行以下 functions.exec 后台单元，把 sid 换成用户给出的 DSH 会话 ID。保留早返回指令，让主聊天可以在等待来信时继续工作。确认事件的顺序是先 notify，再将事件 ID 传给下一次 event。通话静默时保留同一个等待中的事件，仅结束本次 Node REPL 工具调用以避免宿主超时；此时没有查询消息、重新配对或发送回执。

```javascript
// @exec: {"yield_time_ms": 100}
const sid = '用户指定的 session-ID'
const config = await tools.exec_command({cmd: "[pscustomobject]@{thread=$env:CODEX_THREAD_ID;directory=(Join-Path $env:LOCALAPPDATA 'DSH Codex Bridge')}|ConvertTo-Json -Compress"})
if (config.exit_code !== 0) throw Error('无法识别本机 Codex 主聊天')
const {thread, directory} = JSON.parse(config.output)
const modulePath = directory + '/packages/0.7.0/live-client.js'
const slot = 'dshPush_' + sid
const handle = 'globalThis[' + JSON.stringify(slot) + ']'
let setup = handle + "=(await import((await import('node:url')).pathToFileURL(" +
  JSON.stringify(modulePath) + ").href)).startPushPair(" +
  [sid,thread,directory].map(x=>JSON.stringify(x)).join(',') + ');'
let previous
const pending = 'globalThis[' + JSON.stringify(slot + '_pending') + ']'
setup += pending + '=undefined;'
for (;;) {
  const id = previous === undefined ? '' : JSON.stringify(previous)
  const code = setup + `{
    ${pending} ??= ${handle}.event(${id});
    let timer;
    try {
      const keepAlive = new Promise(resolve => {timer = setTimeout(() => resolve({kind:'keepAlive'}), 45000)});
      const event = await Promise.race([${pending},keepAlive]);
      if (event.kind !== 'keepAlive') ${pending} = undefined;
      nodeRepl.write(JSON.stringify(event));
    } finally {clearTimeout(timer)}
  }`
  const result = await tools.mcp__node_repl__js({code, timeout_ms:90000, title:'接通 DSH 实时推送'})
  setup = ''
  if (result.isError) { notify(result.content); break }
  const e = JSON.parse(result.content.find(c=>c.type==='text').text)
  if (e.kind === 'keepAlive') continue
  if (e.kind === 'closed') { if (e.reason) notify(e); break }
  if (e.kind === 'paired') notify({status:'paired',version:e.version,sessionId:e.sessionId})
  else if (e.kind === 'message') notify({source:'DSH 协作方来信',sessionId:e.sessionId,messageId:e.messageId,body:e.body})
  else throw Error('无法识别的推送事件')
  previous = e.id
}
```
