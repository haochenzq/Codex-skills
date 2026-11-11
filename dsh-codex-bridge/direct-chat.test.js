import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import test from 'node:test'
import { createDirectChat, sendCodexMessage } from './direct-chat.js'
import { withCodexService } from './codex-service.js'
import { bridgeError } from './protocol.js'
import { dispatch } from './index.js'

test('direct delivery resumes only an unloaded chat and submits exactly once', async () => {
  for (const status of ['idle', 'active', 'notLoaded']) {
    const target = randomUUID()
    const turnId = randomUUID()
    const calls = []
    const connect = (_cli, run) => run(async (method, params) => {
      assert.equal(params.threadId, target)
      calls.push([method, params])
      if (method === 'thread/read') return { thread: { status: { type: status } } }
      if (method === 'turn/start') return { turn: { id: turnId } }
    })
    const receipt = await sendCodexMessage(target, 'Test message', undefined, connect, async () => null)
    assert.deepEqual(calls.map(([method]) => method), status === 'notLoaded'
      ? ['thread/read', 'thread/resume', 'turn/start'] : ['thread/read', 'turn/start'])
    assert.deepEqual(calls.at(-1)[1].input, [{ type: 'text', text: '【DSH】Test message', text_elements: [] }])
    assert.deepEqual(receipt, { messageId: calls.at(-1)[1].clientUserMessageId, turnId, status: 'sent' })
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

test('a writer conflict before submission rechecks ownership without submitting to the managed service', async () => {
  const target = randomUUID()
  const turnId = randomUUID()
  const calls = []
  const desktop = async () => {
    calls.push('desktop')
    return calls.length === 1 ? null : { turn: { id: turnId } }
  }
  const connect = (_cli, run) => run(async method => {
    calls.push(method)
    if (method === 'thread/read') return { thread: { status: { type: 'notLoaded' } } }
    throw bridgeError('codex-request-rejected', 'thread already has an active writer')
  })
  const receipt = await sendCodexMessage(target, 'Follow the owner', undefined, connect, desktop)
  assert.equal(receipt.turnId, turnId)
  assert.deepEqual(calls, ['desktop', 'thread/read', 'thread/resume', 'desktop'])
})

test('messages use the exact destination selected by the human or the originating Codex chat', async () => {
  const tools = new Map()
  const sent = []
  const chat = createDirectChat({ tools: { register(value) { tools.set(value.name, value) } } }, async (target, message) => {
    sent.push({ target, message })
    return { status: 'sent' }
  })
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
  const input = (rpcId, text) => ({ type: 'user/message', surfaceOp: 'append', data: {
    source: { kind: 'user', rpcId }, content: [{ type: 'text', text }],
  } })
  let events = [{ type: 'turn/start', seq: 1 }, input(prompt.requestId, '')]
  const session = { id: sessionId, seq: 10, snapshotEvents: () => events }
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
  assert.deepEqual(sent, [{ target: from, message: 'Direct reply.' }, { target: selected, message: '已完成。' }])
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
