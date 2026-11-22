import assert from 'node:assert/strict'
import { randomBytes, randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { createTurnChannel, runTurnHook } from './turn-channel.js'

const maintenance = randomUUID()
const production = randomUUID()
const request = (event, threadId, turnId) => ({ event, threadId, turnId })
const input = (event, threadId, turnId) => ({ hook_event_name: event, session_id: threadId, turn_id: turnId,
  prompt: 'must not leave process', tool_response: { private: true } })

test('hooks release messages only into the matching chat and turn, acknowledging after output', async t => {
  const channel = createTurnChannel()
  t.after(channel.close)
  const first = randomUUID(), second = randomUUID()
  channel.hook(request('UserPromptSubmit', maintenance, first))
  channel.hook(request('UserPromptSubmit', production, second))
  const delivered = Promise.all(['one', 'two'].map(body => channel.sendActiveTurn(maintenance, first, body)))
  assert.deepEqual(channel.hook(request('PostToolUse', production, second)), {})
  assert.deepEqual(channel.hook(request('Stop', maintenance, second)), {})
  let output
  const phases = []
  await runTurnHook(input('PostToolUse', maintenance, first), fields => {
    phases.push(fields.event)
    assert.equal('prompt' in fields, false)
    assert.equal('tool_response' in fields, false)
    return channel.hook(fields)
  }, line => { phases.push('stdout'); output = JSON.parse(line) })
  assert.deepEqual(phases, ['PostToolUse', 'stdout', 'ack'])
  assert.equal(output.hookSpecificOutput.hookEventName, 'PostToolUse')
  const messages = JSON.parse(output.hookSpecificOutput.additionalContext.split('\n')[1])
  assert.deepEqual(messages.map(m => m.text), ['one', 'two'])
  assert.deepEqual(await delivered, messages.map(m => ({ messageId: m.messageId, turnId: first, status: 'hook-delivered' })))
  assert.deepEqual(channel.hook(request('PostToolUse', maintenance, first)), {})
})

test('any valid main chat registers, while subagent fields and invalid IDs are filtered before IPC', async () => {
  const id = randomUUID(), turn = randomUUID()
  const channel = createTurnChannel()
  for (const event of ['UserPromptSubmit', 'PreToolUse', 'PostToolUse']) {
    await runTurnHook({ ...input(event, id, turn), agent_id: randomUUID() }, assert.fail, assert.fail)
    await runTurnHook({ ...input(event, id, turn), agent_type: 'worker' }, assert.fail, assert.fail)
    await runTurnHook(input(event, 'invalid', turn), assert.fail, assert.fail)
    await runTurnHook(input(event, id, 'invalid'), assert.fail, assert.fail)
  }
  await runTurnHook(input('UserPromptSubmit', id, turn), channel.hook, assert.fail)
  assert.equal(channel.activeTurn(id), turn)
  channel.close()
})

test('PreToolUse only registers the current turn and cannot claim messages or revive an old turn', async t => {
  const channel = createTurnChannel()
  t.after(channel.close)
  const thread = randomUUID(), active = randomUUID(), next = randomUUID()
  const pre = input('PreToolUse', thread, active)
  await runTurnHook(pre, channel.hook, assert.fail)
  assert.equal(channel.activeTurn(thread), active)
  const delivery = channel.sendActiveTurn(thread, active, 'deliver after tool')
  await runTurnHook(pre, channel.hook, assert.fail)
  await runTurnHook(input('PostToolUse', thread, active), channel.hook,
    line => assert.match(JSON.parse(line).hookSpecificOutput.additionalContext, /deliver after tool/))
  assert.equal((await delivery).turnId, active)
  channel.hook(request('UserPromptSubmit', thread, next))
  await runTurnHook(pre, channel.hook, assert.fail)
  assert.equal(channel.activeTurn(thread), next)
  channel.hook(request('Stop', thread, next))
  await runTurnHook(pre, channel.hook, assert.fail)
  assert.equal(channel.activeTurn(thread), null)
})

test('first tool event recovers an active turn, while terminal and superseded turns remain closed', () => {
  const id = randomUUID(), first = randomUUID(), second = randomUUID(), third = randomUUID()
  const channel = createTurnChannel()
  channel.hook(request('PostToolUse', id, first))
  assert.equal(channel.activeTurn(id), first)
  channel.hook(request('UserPromptSubmit', id, second))
  channel.hook(request('PostToolUse', id, first))
  assert.equal(channel.activeTurn(id), second)
  channel.hook(request('Stop', id, second))
  channel.hook(request('PostToolUse', id, second))
  channel.hook(request('Interrupt', id, third))
  channel.hook(request('PostToolUse', id, third))
  assert.equal(channel.activeTurn(id), null)
  channel.close()
})

test('evicting old terminal records cannot resurrect an old native turn', () => {
  const thread = randomUUID(), channel = createTurnChannel()
  const turnId = i => '019b0000-' + i.toString(16).padStart(4, '0') + '-7000-8010-000000000001'
  for (let i = 0; i < 4100; i++) channel.hook(request('Stop', thread, turnId(i)))
  channel.hook(request('PostToolUse', thread, turnId(0)))
  assert.equal(channel.activeTurn(thread), null)
  channel.hook(request('PostToolUse', thread, turnId(4100)))
  assert.equal(channel.activeTurn(thread), turnId(4100))
  channel.close()
})

test('Stop continues only the matching turn with pending input, then closes it', async () => {
  const channel = createTurnChannel()
  const turn = randomUUID()
  channel.hook(request('UserPromptSubmit', production, turn))
  const accepted = channel.sendActiveTurn(production, turn, 'external context')
  const stop = input('Stop', production, turn)
  await runTurnHook(stop, channel.hook, line => assert.equal(JSON.parse(line).decision, 'block'))
  await accepted
  await runTurnHook(stop, channel.hook, assert.fail)
  assert.equal(channel.activeTurn(production), null)
  channel.hook(request('UserPromptSubmit', production, turn))
  assert.equal(channel.activeTurn(production), null)
  channel.close()
})

test('superseded, interrupted and expired unclaimed messages never follow to another turn', async () => {
  let clock = 0
  const channel = createTurnChannel({ lifetimeMs: 10, now: () => clock })
  const first = randomUUID(), second = randomUUID(), third = randomUUID()
  channel.hook(request('UserPromptSubmit', maintenance, first))
  const replaced = channel.sendActiveTurn(maintenance, first, 'old')
  channel.hook(request('UserPromptSubmit', maintenance, second))
  await assert.rejects(replaced, { code: 'codex-turn-unavailable' })
  const interrupted = channel.sendActiveTurn(maintenance, second, 'interrupted')
  channel.hook(request('Interrupt', maintenance, second))
  await assert.rejects(interrupted, { code: 'codex-turn-unavailable' })
  channel.hook(request('UserPromptSubmit', maintenance, third))
  const expired = channel.sendActiveTurn(maintenance, third, 'expired')
  clock = 11
  assert.deepEqual(channel.hook(request('PostToolUse', maintenance, third)), {})
  await assert.rejects(expired, { code: 'codex-turn-unavailable' })
  channel.close()
})

test('a timeout before a claim is definite, a missing stdout confirmation is ambiguous', async () => {
  const turn = randomUUID()
  const channel = createTurnChannel({ waitMs: 10 })
  channel.hook(request('UserPromptSubmit', maintenance, turn))
  await assert.rejects(channel.sendActiveTurn(maintenance, turn, 'unsent'), { code: 'codex-turn-unavailable' })
  const pending = channel.sendActiveTurn(maintenance, turn, 'maybe')
  await assert.rejects(runTurnHook(input('PostToolUse', maintenance, turn), channel.hook, async () => {
    throw Error('closed stdout')
  }), /closed stdout/)
  await assert.rejects(pending, { code: 'codex-delivery-unknown' })
  assert.deepEqual(channel.hook(request('PostToolUse', maintenance, turn)), {})
  channel.close()
})

test('Windows command hook uses the private endpoint and emits parseable native hook output',
  { skip: process.platform !== 'win32' }, async t => {
    const directory = await mkdtemp(join(tmpdir(), 'dsh-hook-'))
    const pipe = '\\\\.\\pipe\\dsh-codex-' + randomUUID()
    const token = randomBytes(32).toString('hex')
    const turnId = randomUUID()
    const channel = createTurnChannel()
    const server = createServer(socket => {
      let data = ''
      socket.setEncoding('utf8').on('data', chunk => {
        data += chunk
        if (!data.endsWith('\n')) return
        const fields = JSON.parse(data)
        assert.equal(fields.token, token)
        assert.equal(fields.op, 'turn-hook')
        assert.equal('tool_response' in fields, false)
        socket.end(JSON.stringify({ ok: true, value: channel.hook(fields) }) + '\n')
      })
    })
    t.after(async () => {
      channel.close()
      await new Promise(resolve => server.close(resolve))
      await rm(directory, { recursive: true, force: true })
    })
    server.listen(pipe)
    await once(server, 'listening')
    await writeFile(join(directory, 'endpoint.json'), JSON.stringify({ version: 1, token, pipe }))
    async function run(event) {
      const child = spawn(process.execPath, [fileURLToPath(new URL('./turn-channel.js', import.meta.url))],
        { env: { ...process.env, DSH_CODEX_BRIDGE_DIR: directory }, windowsHide: true })
      let stdout = ''
      child.stdout.setEncoding('utf8').on('data', chunk => { stdout += chunk })
      child.stdin.end(JSON.stringify(input(event, maintenance, turnId)))
      const [code] = await once(child, 'close')
      assert.equal(code, 0)
      return stdout
    }
    assert.equal(await run('UserPromptSubmit'), '')
    assert.equal(channel.activeTurn(maintenance), turnId)
    const receipt = channel.sendActiveTurn(maintenance, turnId, 'Windows pipe')
    const output = JSON.parse(await run('PostToolUse'))
    assert.match(output.hookSpecificOutput.additionalContext, /Windows pipe/)
    assert.equal((await receipt).status, 'hook-delivered')
  })
