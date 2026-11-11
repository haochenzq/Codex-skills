import assert from 'node:assert/strict'
import { createHash, randomUUID } from 'node:crypto'
import test from 'node:test'
import { readAttachments } from './attachments.js'
import { dispatch } from './index.js'

test('one history page locates text, attachments and tool results without exporting tool internals', async () => {
  const sessionId = 'session-example'
  const png = Buffer.from('fixture image')
  const sha256 = createHash('sha256').update(png).digest('hex')
  const attachmentId = 'sha256:' + sha256
  const ref = { attachmentId, mediaType: 'image/png', bytes: png.length }
  const rows = [
    { event: { seq: 7, type: 'assistant/message', data: { content: 'Visible response' } } },
    { event: { seq: 8, type: 'tool/result', data: { turn: 2, message: {
      name: 'example', isError: false, content: [{ type: 'text', text: '{"exitCode":0}' },
        { type: 'image', attachment: ref }, { type: 'reasoning', text: 'Private detail' }],
    } } } },
  ]
  let requests = 0
  let reads = 0
  const invoke = async (method, args) => {
    if (method === 'events') {
      requests++
      assert.equal(args.request.address.sessionId, sessionId)
      return { cursor: 8, records: args.request.throughSeq === undefined ? rows :
        rows.filter(({ event }) => event.seq === args.request.throughSeq) }
    }
    assert.equal(method, 'attachment')
    reads++
    return { data: png.toString('base64') }
  }
  const history = await dispatch({ op: 'history', sessionId }, invoke)
  assert.equal(requests, 1)
  assert.deepEqual(history.messages.map(message => message.text), ['Visible response'])
  assert.equal(history.attachments[0].attachment.attachmentId, attachmentId)
  assert.equal(history.toolResults[0].seq, 8)
  assert.ok(!JSON.stringify(history).includes('exitCode'))
  const tool = await dispatch({ op: 'tool-result', sessionId, seq: 8 }, invoke)
  assert.equal(tool.text, '{"exitCode":0}')
  assert.equal(tool.attachments.length, 1)
  await assert.rejects(dispatch({ op: 'tool-result', sessionId, seq: 7 }, invoke), { code: 'tool-result-not-found' })
  const data = await readAttachments({}, sessionId, { op: 'attachment-data', seq: 8, attachmentId }, invoke)
  assert.equal(reads, 1)
  assert.deepEqual(Buffer.from(data.data, 'base64'), png)
  assert.equal(data.sha256, sha256)
})

test('sending a file uses a native prompt content part and preserves request identity', async () => {
  const sessionId = 'session-example'
  const requestId = randomUUID()
  const filePath = '/fixtures/image.png'
  const attachment = { type: 'image', attachment: { name: 'image.png' } }
  const result = await dispatch({ op: 'send', sessionId, requestId, text: 'Check this.', filePath },
    async (method, args) => {
      assert.equal(method, 'prompt')
      return args.request
    }, async path => {
      assert.equal(path, filePath)
      return attachment
    })
  assert.equal(result.requestId, 'codex-bridge:' + requestId)
  assert.deepEqual(result.content, [{ type: 'text', text: '【Codex】Check this.' }, attachment])
})
