import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { dispatch, visibleText } from './index.js'
import { taskPrefix } from './protocol.js'
import { createTasks } from './tasks.js'

test('a long DSH reply can be recovered without splitting Unicode or exporting internal content', async () => {
  const body = '文'.repeat(23_999) + '😀' + '后续正文'.repeat(8_000)
  const records = [
    { event: { seq: 2, type: 'user/message', surfaceOp: 'append', data: {
      source: { kind: 'runtime-context' }, content: [{ type: 'text', text: 'internal' }],
    } } },
    { event: { seq: 3, type: 'assistant/message', data: { message: { content: [
      { type: 'thinking', text: 'hidden' }, { type: 'text', text: body },
    ] } } } },
  ]
  const invoke = async () => ({ records, cursor: 3, hasMore: false })
  const sessionId = 'session-text'
  const page = await dispatch({ op: 'history', sessionId }, invoke)
  assert.deepEqual(page.messages.map(message => message.seq), [3])
  assert.equal(page.messages[0].nextOffset, 23_999)
  let result = page.messages[0].text
  let offset = page.messages[0].nextOffset
  while (offset !== undefined) {
    const chunk = await dispatch({ op: 'message', sessionId, seq: 3, offset }, invoke)
    result += chunk.text
    offset = chunk.nextOffset
  }
  assert.equal(result, body)
})

test('a delegated turn restricts tools, detects user steering, and survives a same-ID retry', async () => {
  const workspace = mkdtempSync(join(tmpdir(), 'codex-dsh-test-'))
  const sessionId = 'session-test'
  const id = randomUUID()
  const requestId = taskPrefix + id
  const events = []
  const callbacks = new Map()
  let guard, tool, sent = 0
  const ctx = {
    on(name, listener) { callbacks.set(name, listener) },
    tools: {
      guard(callback) { guard = callback },
      register(definition) { if (definition.name === 'codex_read_task_file') tool = definition },
    },
  }
  const agent = { status: 'running', session: { id: sessionId, snapshotEvents: () => events } }
  const append = (type, data) => events.push({ type, data, seq: events.length })
  const invoke = async (method, args) => {
    if (method === 'list') return { items: [{ sessionId, cwd: workspace }] }
    if (method === 'state') return { cursor: events.length - 1, running: agent.status === 'running', queue: [], pendingInput: [] }
    if (method === 'events') return { records: events.slice(0, args.request.throughSeq + 1).map(event => ({ event })), hasMore: false }
    if (method === 'prompt') {
      sent++
      append('agent/inbox/spliced', { inserted: [{ source: { kind: 'user', rpcId: requestId } }] })
      append('turn/start', { turn: 1 })
      callbacks.get('agent/inbox/claimed')({ agent, turn: 1, message: { source: { rpcId: requestId } } })
      append('user/message', { source: { kind: 'user', rpcId: requestId } })
      return { accepted: true }
    }
    throw new Error('Unexpected method: ' + method)
  }
  const signal = new AbortController().signal
  try {
    writeFileSync(join(workspace, 'allowed.txt'), 'first\nsecond\n')
    writeFileSync(join(workspace, 'outside-scope.txt'), 'excluded')
    const tasks = createTasks(ctx, join(workspace, 'journal'), visibleText)
    const submit = { op: 'submit', taskId: id, task: {
      workspace, scope: 'read-only', files: ['allowed.txt'], goal: 'Read the allowed file.',
      deliverable: 'Line count', acceptance: 'Independent count',
    } }
    assert.equal((await tasks.handle(sessionId, submit, invoke, signal)).status, 'running')
    assert.match(guard({ agent, name: 'bash' }), /allowlisted/)
    assert.throws(() => tool.execute({ file: 'outside-scope.txt' }, { agent, signal }), /allowlist/)
    assert.equal(JSON.parse(tool.execute({ file: 'allowed.txt' }, { agent, signal })).lines, 2)

    append('user/message', { source: { kind: 'user', rpcId: 'human-steering' } })
    append('assistant/message', { content: [{ type: 'text', text: 'Two lines.' }] })
    append('turn/end', { turn: 1, reason: { kind: 'completed' } })
    callbacks.get('session/event')(agent.session, events.at(-1))
    agent.status = 'idle'
    assert.equal(guard({ agent, name: 'bash' }), undefined)
    const waiting = await tasks.handle(sessionId, { op: 'wait', taskId: id, seconds: 1 }, invoke, signal)
    assert.equal(waiting.status, 'needs-review')
    assert.deepEqual(waiting.resultSeqs, [4])
    const review = { op: 'review', taskId: id, decision: 'accept', evidence: 'Independently counted two lines.' }
    assert.equal((await tasks.handle(sessionId, review, invoke, signal)).status, 'verified')
    assert.equal((await tasks.handle(sessionId, review, invoke, signal)).status, 'verified')
    assert.equal((await tasks.handle(sessionId, submit, invoke, signal)).status, 'verified')
    assert.equal(sent, 1)
  } finally {
    const temporary = realpathSync(workspace)
    assert.ok(temporary.startsWith(join(realpathSync(tmpdir()), 'codex-dsh-test-')))
    rmSync(temporary, { recursive: true })
  }
})
