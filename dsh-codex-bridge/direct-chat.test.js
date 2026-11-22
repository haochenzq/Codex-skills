import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { createDirectChat, resolveMainCodexThread, sendCodexMessage } from './direct-chat.js'
import { deliverToDesktopOwner } from './codex-desktop.js'
import { withCodexService } from './codex-service.js'
import { bridgeError } from './protocol.js'
import { dispatch } from './index.js'

function routeDirectory(t) {
  const directory = mkdtempSync(join(tmpdir(), 'dsh-codex-routes-'))
  t.after(() => rmSync(directory, { recursive: true, force: true }))
  return directory
}

function input(rpcId, text) {
  return { type: 'user/message', surfaceOp: 'append', data: {
    source: { kind: 'user', rpcId }, content: [{ type: 'text', text }],
  } }
}

function chatTools(directory, sent, findAttachment, resolveMain = async id => id) {
  const tools = new Map()
  const chat = createDirectChat({ tools: { register(value) { tools.set(value.name, value) } } },
    directory, async (target, message, attachment) => {
      sent.push({ target, message, ...(attachment === undefined ? {} : { attachment }) })
      return { status: 'sent' }
    }, findAttachment, resolveMain)
  return { tools, chat }
}

function testSession(id, events) {
  return { id, get seq() { return events.length }, snapshotEvents: (from, to) => events.slice(from, to) }
}

test('queue fallback submits once without acquiring the writer for any chat state', async () => {
  for (const status of ['idle', 'active', 'notLoaded']) {
    const target = randomUUID()
    const turnId = randomUUID()
    const calls = []
    const connect = (_cli, run) => run(async (method, params) => {
      assert.equal(params.threadId, target)
      calls.push([method, params])
      if (method === 'thread/read') return { thread: { status: { type: status } } }
      if (method === 'thread/queue/add') return { queuedSubmission: { id: turnId, clientUserMessageId: params.clientUserMessageId } }
    })
    const receipt = await sendCodexMessage(target, 'Test message', undefined, connect, async () => null)
    assert.deepEqual(calls.map(([method]) => method), ['thread/read', 'thread/queue/add'])
    assert.deepEqual(calls.at(-1)[1].input, [{ type: 'text', text: '【DSH】Test message', text_elements: [] }])
    assert.deepEqual(receipt, { messageId: calls.at(-1)[1].clientUserMessageId, queueId: turnId, status: 'queued' })
  }
})

test('a desktop-owned thread never goes through the managed service', async () => {
  const target = randomUUID()
  const turnId = randomUUID()
  const receipt = await sendCodexMessage(target, 'Desktop reply', undefined, () => assert.fail(), async request => {
    assert.equal(request.threadId, target)
    assert.equal(request.input[0].text, '【DSH】Desktop reply')
    return { turn: { id: turnId } }
  })
  assert.equal(receipt.turnId, turnId)
  await assert.rejects(sendCodexMessage(target, 'Unknown delivery', undefined, () => assert.fail(), async () => {
    throw bridgeError('codex-delivery-unknown', 'Desktop receipt missing')
  }), { code: 'codex-delivery-unknown' })
})

test('desktop delivery steers an active turn without starting a provisional turn', async () => {
  const request = { threadId: randomUUID(), clientUserMessageId: randomUUID(),
    input: [{ type: 'text', text: '【DSH】Follow-up', text_elements: [] }] }
  const turnId = randomUUID()
  let calls = 0
  const result = await deliverToDesktopOwner(request, 'owner', async (method, version, params, target) => {
    calls++
    assert.equal(method, 'thread-follower-steer-turn')
    assert.equal(version, 1)
    assert.equal(target, 'owner')
    assert.equal(params.conversationId, request.threadId)
    assert.equal(params.clientUserMessageId, request.clientUserMessageId)
    assert.equal(params.restoreMessage.id, request.clientUserMessageId)
    assert.equal(params.input, request.input)
    return { resultType: 'success', handledByClientId: 'owner', result: { result: { turnId } } }
  }, () => assert.fail('unexpected delivery failure'))
  assert.deepEqual(result, { turn: { id: turnId } })
  assert.equal(calls, 1)
})

test('desktop delivery opens a turn only after a definite inactive-turn rejection', async () => {
  const request = { threadId: randomUUID(), clientUserMessageId: randomUUID(), input: [] }
  const turn = { id: randomUUID() }
  const calls = []
  const failure = () => bridgeError('codex-delivery-unknown', 'Delivery could not be confirmed')
  const result = await deliverToDesktopOwner(request, 'owner', async (method, version, params, target) => {
    calls.push(method)
    if (method === 'thread-follower-steer-turn') return { resultType: 'error',
      error: `Cannot steer conversation ${request.threadId} because its active turn already ended` }
    assert.equal(target, 'owner')
    assert.equal(params.turnStart.request, request)
    return { resultType: 'success', handledByClientId: 'owner', result: { result: { turn } } }
  }, failure)
  assert.deepEqual(result, { turn })
  assert.deepEqual(calls, ['thread-follower-steer-turn', 'thread-follower-start-turn'])

  for (const response of [{ resultType: 'error', error: 'timeout' }, { resultType: 'success', handledByClientId: 'owner' }]) {
    await assert.rejects(deliverToDesktopOwner(request, 'owner', async method => {
      assert.equal(method, 'thread-follower-steer-turn')
      return response
    }, failure), { code: 'codex-delivery-unknown' })
  }
})

test('a pre-submission desktop failure may queue but a mismatched receipt stays unconfirmed', async () => {
  const connect = (_cli, run) => run(async method => {
    if (method === 'thread/read') return { thread: {} }
    assert.equal(method, 'thread/queue/add')
    return { queuedSubmission: { id: randomUUID(), clientUserMessageId: randomUUID() } }
  })
  await assert.rejects(sendCodexMessage(randomUUID(), 'Check receipt', undefined, connect, async () => {
    throw bridgeError('codex-desktop-unavailable', 'Owner discovery unavailable')
  }), { code: 'codex-delivery-unknown' })
})

test('thread metadata resolves nested sub-agents without redirecting a regular fork', async () => {
  const root = randomUUID()
  const child = randomUUID()
  const nested = randomUUID()
  const fork = randomUUID()
  const children = new Map([[child, root], [nested, child]])
  const calls = []
  const connect = (_cli, run) => run(async (method, { threadId, includeTurns }) => {
    assert.equal(method, 'thread/read')
    assert.equal(includeTurns, false)
    calls.push(threadId)
    const parent = children.get(threadId)
    return { thread: { id: threadId, forkedFromId: root, source: parent
      ? { subAgent: { thread_spawn: { parent_thread_id: parent } } } : 'vscode' } }
  })
  assert.equal(await resolveMainCodexThread(nested, connect), root)
  assert.equal(await resolveMainCodexThread(fork, connect), fork)
  assert.deepEqual(calls, [nested, child, root, fork])
  assert.equal(await resolveMainCodexThread(child, async () => { throw new Error('offline') }), child)
})

test('implicit sub-agent replies use the main chat and existing duplicate pairings resolve to one target', async t => {
  const directory = routeDirectory(t)
  const root = randomUUID()
  const child = randomUUID()
  const sessionId = 'session-dsh'
  const sent = []
  const resolveMain = async (id, ...extra) => {
    assert.deepEqual(extra, [])
    return id === child ? root : id
  }
  const { tools, chat } = chatTools(directory, sent, undefined, resolveMain)
  const requestId = randomUUID()
  const request = { sessionId, requestId, codexThreadId: child }
  await chat.submit(request, async () => ({ accepted: true }))
  await assert.rejects(chat.submit({ ...request, replyTo: child }, () => assert.fail('Unexpected dispatch')),
    { code: 'codex-subagent-target' })
  const routeDirectoryPath = join(directory, 'codex-routes')
  const routeFile = join(routeDirectoryPath, sessionId + '.json')
  assert.deepEqual(JSON.parse(readFileSync(routeFile, 'utf8')), [root])
  const reply = tools.get('reply_to_codex')
  const current = testSession(sessionId, [{ type: 'turn/start', seq: 0 }, input('codex-bridge:' + requestId, '')])
  await reply.execute({ message: 'Current' }, { agent: { session: current } })
  mkdirSync(routeDirectoryPath, { recursive: true })
  writeFileSync(routeFile, JSON.stringify([root, child]))
  const restarted = chatTools(directory, sent, undefined, resolveMain)
  const later = testSession(sessionId, [{ type: 'turn/start', seq: 9 }])
  await restarted.tools.get('reply_to_codex').execute({ message: 'Later' }, { agent: { session: later } })
  await assert.rejects(restarted.tools.get('send_to_codex').execute({ message: 'Explicit', target: child },
    { agent: { session: later } }), { code: 'codex-subagent-target' })
  assert.deepEqual(sent, [{ target: root, message: 'Current' }, { target: root, message: 'Later' }])
})

test('explicit sub-agent rejection is reported without retry or alternate delivery', async () => {
  const request = { threadId: randomUUID(), clientUserMessageId: randomUUID(), input: [] }
  const rejection = { resultType: 'error', error: 'direct app-server input is not allowed for multi-agent v2 sub-agents' }
  await assert.rejects(deliverToDesktopOwner(request, 'owner', async method => {
    assert.equal(method, 'thread-follower-steer-turn')
    return rejection
  }, () => assert.fail('Unexpected fallback')), { code: 'codex-subagent-target' })
  const connect = (_cli, run) => run(async method => {
    assert.equal(method, 'thread/read')
    return { thread: { source: { subAgent: { thread_spawn: {} } } } }
  })
  await assert.rejects(sendCodexMessage(request.threadId, 'Test', undefined, connect, async () => null),
    { code: 'codex-subagent-target' })
})

test('messages use the exact destination selected by the human or the originating Codex chat', async t => {
  const directory = routeDirectory(t)
  const sent = []
  const { tools, chat } = chatTools(directory, sent)
  const from = randomUUID()
  const selected = randomUUID()
  const sessionId = 'session-dsh'
  const requestId = randomUUID()
  const request = { op: 'send', sessionId, codexThreadId: from, requestId, text: 'Send a reply.' }
  const prompt = await chat.submit(request, payload => dispatch(payload, (method, args) => {
    assert.equal(method, 'prompt')
    return args.request
  }))
  assert.equal(prompt.content[0].text, '【Codex】Send a reply.')
  assert.equal(prompt.sessionId, sessionId)
  assert.equal(prompt.mode, 'steer')
  let events = [{ type: 'turn/start', seq: 1 }, input(prompt.requestId, '')]
  const session = { id: sessionId, get seq() { return events.length }, snapshotEvents: (from, to) => events.slice(from, to) }
  const send = (message, target, to = session) => tools.get('send_to_codex').execute({ message, target }, { agent: { session: to } })
  const textReply = tools.get('reply_to_codex')
  const reply = (message, to = session) => textReply.execute({ message }, { agent: { session: to } })
  assert.deepEqual(Object.keys(textReply.parameters.properties), ['message'])
  await assert.rejects(send('Wrong target', selected), { code: 'codex-target-not-authorized' })
  await assert.rejects(send('Wrong DSH chat', from, { ...session, id: 'session-other' }), { code: 'codex-target-not-authorized' })
  await reply('Direct reply.')
  await send('Direct reply.', '')
  await assert.rejects(reply('Wrong DSH chat', { ...session, id: 'session-other' }), { code: 'codex-target-not-authorized' })
  events.push(input('human-other', '请联系 Codex 线程：codex://threads/' + selected + '，发消息说已完成。'))
  await assert.rejects(reply('Ambiguous target'), { code: 'codex-target-not-authorized' })
  await assert.rejects(send('Ambiguous blank target', ' '), { code: 'codex-target-not-authorized' })
  events = [{ type: 'turn/start', seq: 12 }, input('human', '请联系 Codex 线程：codex://threads/' + selected + '，发消息说已完成。')]
  await send('已完成。')
  await assert.rejects(send('Old target', from), { code: 'codex-target-not-authorized' })
  events.push({ type: 'turn/end', seq: 15 })
  await assert.rejects(send('Expired turn', selected), { code: 'codex-target-not-authorized' })
  await assert.rejects(reply('Expired turn'), { code: 'codex-target-not-authorized' })
  events.push({ type: 'turn/start', seq: 16 }, input('human-later', '请把下一步发给 Codex。'))
  await reply('下一步。')
  assert.deepEqual(sent, [{ target: from, message: 'Direct reply.' }, { target: selected, message: '已完成。' },
    { target: selected, message: '下一步。' }])
})

test('an accepted Codex message pairs text and attachments with only the selected DSH session', async t => {
  const directory = routeDirectory(t)
  const first = randomUUID()
  const unknown = randomUUID()
  const rejected = randomUUID()
  const alternate = randomUUID()
  const sessionId = 'session-dsh'
  const sent = []
  const { chat } = chatTools(directory, sent)
  await chat.submit({ sessionId, requestId: randomUUID(), codexThreadId: first }, async () => ({ accepted: true }))
  await assert.rejects(chat.submit({ sessionId, requestId: randomUUID(), codexThreadId: rejected },
    async () => { throw new Error('Rejected by DSH') }), /Rejected by DSH/)
  await chat.submit({ sessionId, requestId: randomUUID(), codexThreadId: rejected, replyTo: alternate },
    async () => ({ accepted: true }))

  const attachment = { kind: 'image', mediaType: 'image/png', data: 'test' }
  const attachmentId = 'sha256:' + 'a'.repeat(64)
  const { tools, chat: restarted } = chatTools(directory, sent, async (session, digest, seq) => {
    assert.equal(session.id, sessionId)
    assert.equal(digest, attachmentId)
    assert.equal(seq, 3)
    return attachment
  })
  const events = [{ type: 'turn/start', seq: 0 }, input('human', '请主动联系 Codex。')]
  const session = testSession(sessionId, events)
  const exec = { agent: { session } }
  const send = tools.get('send_to_codex')
  const reply = tools.get('reply_to_codex')
  await reply.execute({ message: 'Progress update' }, exec)
  await send.execute({ message: 'Progress update', target: first }, exec)
  for (const target of [unknown, rejected, alternate]) {
    await assert.rejects(send.execute({ message: 'Unknown', target }, exec), { code: 'codex-target-not-authorized' })
    await assert.rejects(send.execute({ message: 'Unknown', target, attachmentId, sourceSeq: 3 }, exec),
      { code: 'codex-target-not-authorized' })
  }
  await assert.rejects(reply.execute({ message: 'Wrong DSH session' },
    { agent: { session: testSession('session-unpaired', events) } }), { code: 'codex-target-not-authorized' })
  await assert.rejects(send.execute({ message: 'Wrong DSH session', attachmentId, sourceSeq: 3 },
    { agent: { session: testSession('session-unpaired', events) } }), { code: 'codex-target-not-authorized' })
  await send.execute({ message: 'Paired attachment', attachmentId, sourceSeq: 3 }, exec)
  await send.execute({ message: 'Paired attachment', target: first, attachmentId, sourceSeq: 3 }, exec)
  const requestId = randomUUID()
  await restarted.submit({ sessionId, requestId, codexThreadId: first }, async () => ({ accepted: true }))
  events.push(input('codex-bridge:' + requestId, 'Please send the authorized attachment.'))
  await send.execute({ message: 'Attachment', attachmentId, sourceSeq: 3 }, exec)
  assert.deepEqual(sent, [
    { target: first, message: 'Progress update' },
    { target: first, message: 'Paired attachment', attachment },
    { target: first, message: 'Attachment', attachment },
  ])
})

test('multiple paired destinations require a selection and a long active turn keeps its original authorization', async t => {
  const directory = routeDirectory(t)
  const sent = []
  const { tools, chat } = chatTools(directory, sent)
  const first = randomUUID()
  const second = randomUUID()
  const priorTurn = randomUUID()
  const sessionId = 'session-dsh'
  for (const codexThreadId of [first, second]) {
    await chat.submit({ sessionId, requestId: randomUUID(), codexThreadId }, async () => ({ accepted: true }))
  }
  const events = [
    { type: 'turn/start', seq: 0 },
    input('prior-human', '请联系 Codex ' + priorTurn),
    { type: 'turn/end', seq: 2 },
    { type: 'turn/start', seq: 3 },
  ]
  const exec = { agent: { session: testSession(sessionId, events) } }
  const send = tools.get('send_to_codex')
  const reply = tools.get('reply_to_codex')
  await assert.rejects(reply.execute({ message: 'Ambiguous' }, exec), /several paired Codex chats/)
  await send.execute({ message: 'Explicit pairing', target: 'codex://threads/' + second }, exec)
  const requestId = randomUUID()
  await chat.submit({ sessionId, requestId, codexThreadId: first }, async () => ({ accepted: true }))
  events.push(input('codex-bridge:' + requestId, 'The current destination.'))
  const appendSteps = () => {
    for (let i = 0; i < 550; i++) events.push({ type: 'step/end', seq: events.length })
  }
  appendSteps()
  await reply.execute({ message: 'Same active turn' }, exec)
  appendSteps()
  await reply.execute({ message: 'Same active turn' }, exec)
  await assert.rejects(send.execute({ message: 'Previous turn', target: priorTurn }, exec),
    { code: 'codex-target-not-authorized' })
  assert.deepEqual(sent, [{ target: second, message: 'Explicit pairing' }, { target: first, message: 'Same active turn' }])
})

test('direct delivery starts the daemon and reconnects once after a refused handshake', async () => {
  const calls = []
  const deliver = () => ({ status: 'sent' })
  const connect = async (cli, run) => {
    calls.push(['connect', cli])
    if (calls.length === 1) throw bridgeError('codex-control-unreachable', 'Connection refused')
    return run()
  }
  const start = async cli => { calls.push(['start', cli]) }
  assert.deepEqual(await withCodexService('codex.exe', deliver, connect, start), { status: 'sent' })
  assert.deepEqual(calls, [['connect', 'codex.exe'], ['start', 'codex.exe'], ['connect', 'codex.exe']])
})

test('direct delivery never reconnects after an unknown outcome', async () => {
  let attempts = 0
  const connect = async () => {
    attempts++
    throw bridgeError('codex-delivery-unknown', 'Connection dropped during delivery')
  }
  await assert.rejects(withCodexService('codex.exe', () => assert.fail(), connect, () => assert.fail()),
    { code: 'codex-delivery-unknown' })
  assert.equal(attempts, 1)
})

test('addressed plain text can reach two paired chats in an independent director turn', async t => {
  const sent = []
  const { chat, tools } = chatTools(routeDirectory(t), sent)
  const sessionId = 'session-director'
  const targets = [randomUUID(), randomUUID()]
  for (const target of targets) {
    await chat.submit({ sessionId, requestId: randomUUID(), codexThreadId: target }, async () => ({ accepted: true }))
  }
  const exec = { agent: { session: testSession(sessionId, [{ type: 'turn/start', seq: 7 }]) } }
  const tool = tools.get('send_text_to_codex')
  assert.deepEqual(tool.parameters.required, ['target', 'message'])
  for (const target of targets) await tool.execute({ target, message: 'Ready' }, exec)
  await assert.rejects(tool.execute({ target: randomUUID(), message: 'Wrong' }, exec), { code: 'codex-target-not-authorized' })
  assert.deepEqual(sent, targets.map(target => ({ target, message: 'Ready' })))
})

test('active-only delivery requires an authorized target and preserves the strict flag', async t => {
  const registered = new Map()
  const target = randomUUID()
  const ctx = { tools: { register(tool) { registered.set(tool.name, tool) } } }
  let attempts = 0
  const chat = createDirectChat(ctx, routeDirectory(t), async (id, text, attachment, activeOnly) => {
    attempts++
    assert.deepEqual([id, text, attachment, activeOnly], [target, 'During this turn', undefined, true])
    throw bridgeError('codex-turn-unavailable', 'No active turn')
  }, undefined, async id => id)
  const sessionId = 'session-director'
  await chat.submit({ sessionId, requestId: randomUUID(), codexThreadId: target }, async () => ({ accepted: true }))
  const exec = { agent: { session: testSession(sessionId, [{ type: 'turn/start', seq: 0 }]) } }
  const tool = registered.get('send_to_active_codex')
  await assert.rejects(tool.execute({ target: randomUUID(), message: 'During this turn' }, exec),
    { code: 'codex-target-not-authorized' })
  await assert.rejects(tool.execute({ target, message: 'During this turn' }, exec),
    { code: 'codex-turn-unavailable' })
  assert.equal(attempts, 1)
})
