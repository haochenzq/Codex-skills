import { randomUUID } from 'node:crypto'
import { existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { bridgeError, dshSessionId, requestPrefix, requestUuid } from './protocol.js'
import { withCodexService } from './codex-service.js'
import { sendThroughDesktop } from './codex-desktop.js'

const originLifetime = 30 * 60 * 1000

function threadId(value) {
  if (typeof value !== 'string') return null
  const id = value.trim().replace(/^codex:\/\/threads\//i, '')
  return requestUuid.test(id) ? id.toLowerCase() : null
}

export async function sendCodexMessage(target, message, attachment, connect = withCodexService, desktop = sendThroughDesktop) {
  const home = process.env.CODEX_HOME || join(homedir(), '.codex')
  const managed = join(home, 'packages', 'app-server-daemon', 'current', 'bin', 'codex.exe')
  const cli = existsSync(managed) ? managed : 'codex.exe'
  const body = '【DSH】' + message.replace(/^【DSH】\s*/, '')
  if (attachment && attachment.kind !== 'file' && attachment.kind !== 'image') {
    throw bridgeError('invalid-attachment', 'The verified attachment has an unsupported delivery type.')
  }
  const text = attachment?.kind === 'file'
    ? body + '\n\nDSH 本机原文件 ' + JSON.stringify(attachment.name) +
      '\n路径 ' + JSON.stringify(attachment.path) + '\nSHA-256 ' + attachment.sha256
    : body
  const input = [{ type: 'text', text, text_elements: [] }]
  if (attachment?.kind === 'image') {
    input.push({ type: 'image', url: 'data:' + attachment.mediaType + ';base64,' + attachment.data })
  }
  const messageId = randomUUID()
  const request = { threadId: target, clientUserMessageId: messageId, input }
  let result = await desktop(request)
  if (result === null) {
    try {
      result = await connect(cli, async rpc => {
        const { thread } = await rpc('thread/read', { threadId: target, includeTurns: false })
        if (thread.status.type === 'notLoaded') {
          try {
            await rpc('thread/resume', { threadId: target, excludeTurns: true })
          } catch (error) {
            if (error.code !== 'codex-request-rejected' || !/already has an active writer/i.test(error.message)) throw error
            throw bridgeError('codex-active-writer', error.message)
          }
        }
        return rpc('turn/start', request)
      })
    } catch (error) {
      if (error.code !== 'codex-active-writer') throw error
      // Desktop may have acquired the session after the initial owner lookup.
      result = await desktop(request)
      if (result === null) throw bridgeError('codex-owner-unavailable',
        'Another Codex process owns this conversation and its desktop route is unavailable. The message was not sent.')
    }
  }
  const { turn } = result
  if (!turn?.id) throw bridgeError('codex-delivery-unknown', 'Codex did not return a turn receipt. Check the target before retrying.')
  return { messageId, turnId: turn.id, status: 'sent',
    ...(attachment ? { attachment: attachment.kind === 'image' ? 'image' : 'file-reference' } : {}) }
}

export function createDirectChat(ctx, send = sendCodexMessage, findAttachment) {
  const origins = new Map()
  const sent = new Map()

  ctx.tools.register({
    name: 'send_to_codex',
    description: 'For plain-text replies to the originating Codex chat, use reply_to_codex. Send a 【DSH】 message to an existing Codex chat. During an authorized joint task, advance your assigned work and proactively contact Codex with evidence, a decision needed to unblock work, or a verified completion. Include the task and the next action for Codex when there is one. Continue within scope when Codex sends feedback. Stop when the agreed work is complete. Do not reply to acknowledgments or expand the task. Omit target when replying to a Codex message in this turn. For a new message, the human must select a Codex link or UUID in this turn. Optional attachmentId must be an authorized native attachment in this DSH chat. The bridge selects delivery automatically: native images stay images, other files use verified local references. Never invent an attachmentId or sourceSeq. If delivery status is unknown, check the target before retrying.',
    parameters: {
      type: 'object', additionalProperties: false, required: ['message'],
      properties: { target: { type: 'string' }, message: { type: 'string', minLength: 1, maxLength: 4000 },
        attachmentId: { type: 'string', pattern: '^sha256:[a-f0-9]{64}$' }, sourceSeq: { type: 'integer', minimum: 0 } },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    execute: deliver,
  })

  ctx.tools.register({
    name: 'reply_to_codex',
    description: 'Reply in plain text to the one Codex chat authorized in the current DSH turn. Use this for a completed handoff, an evidence request, or a concrete blocker. Provide only the message. If the origin is unavailable, leave the result in this DSH chat and do not retry.',
    parameters: {
      type: 'object', additionalProperties: false, required: ['message'],
      properties: { message: { type: 'string', minLength: 1, maxLength: 4000 } },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    execute({ message }, exec) {
      return deliver({ message }, exec)
    },
  })

  async function deliver({ target, message, attachmentId, sourceSeq }, exec) {
    const session = exec.agent?.session
    if (!dshSessionId.test(session?.id) || typeof message !== 'string' || !message.trim() || message.length > 4000) {
      throw bridgeError('invalid-codex-message', 'A message requires 1–4,000 characters in a DSH conversation.')
    }
    const events = session.snapshotEvents(Math.max(0, session.seq - 500))
    const start = events.findLastIndex(event => event.type === 'turn/start' || event.type === 'turn/end')
    const live = events[start]?.type === 'turn/start' ? events.slice(start + 1) : []
    const choices = new Set()
    for (const event of live) {
      const source = event.data?.source
      if (event.type !== 'user/message' || event.surfaceOp !== 'append' || source?.kind !== 'user' ||
          typeof source.rpcId !== 'string') continue
      if (source.rpcId.startsWith(requestPrefix)) {
        const origin = origins.get(source.rpcId)
        if (origin?.sessionId === session.id && origin.expiresAt > Date.now()) choices.add(origin.target)
        continue
      }
      const content = event.data.content
      const text = typeof content === 'string' ? content : Array.isArray(content)
        ? content.filter(part => part.type === 'text').map(part => part.text).join('') : ''
      if (!/codex/i.test(text) || !/联系|发(?:一条)?消息/.test(text)) continue
      const targets = new Set([...text.matchAll(/(?:codex:\/\/threads\/)?\b[a-f0-9-]{36}\b/gi)]
        .map(match => threadId(match[0])).filter(Boolean))
      if (targets.size === 1) choices.add([...targets][0])
    }
    const automaticTarget = target === undefined || (typeof target === 'string' && !target.trim())
    const requested = automaticTarget && choices.size === 1 ? [...choices][0] : threadId(target)
    if (!choices.has(requested)) {
      throw bridgeError('codex-target-not-authorized', 'Use the origin of the current Codex message, or have the human explicitly select a Codex chat in this turn.')
    }
    const body = message.trim()
    const key = JSON.stringify([session.id, events[start].seq, requested, body, attachmentId, sourceSeq])
    const now = Date.now()
    for (const [oldKey, entry] of sent) {
      if (entry.expiresAt <= now) sent.delete(oldKey)
    }
    let delivery = sent.get(key)
    if (!delivery) {
      delivery = { result: (async () => send(requested, body,
        attachmentId === undefined ? undefined : await findAttachment(session, attachmentId, sourceSeq, exec.signal)))(),
      expiresAt: now + originLifetime }
      sent.set(key, delivery)
    }
    return JSON.stringify(await delivery.result)
  }

  async function submit(request, dispatch) {
    const target = threadId(request.replyTo ?? request.codexThreadId)
    if (request.replyTo !== undefined && !target) {
      throw bridgeError('invalid-reply-target', 'Choose an existing Codex chat link or ID.')
    }
    if (target && typeof request.requestId === 'string' && requestUuid.test(request.requestId)) {
      const now = Date.now()
      for (const [key, origin] of origins) {
        if (origin.expiresAt <= now) origins.delete(key)
      }
      const key = requestPrefix + request.requestId.toLowerCase()
      const current = origins.get(key)
      if (current && (current.target !== target || current.sessionId !== request.sessionId)) {
        throw bridgeError('request-conflict', 'This request ID already belongs to another conversation.')
      }
      if (!current) origins.set(key, { target, sessionId: request.sessionId, expiresAt: now + originLifetime })
    }
    return dispatch(request)
  }

  return { submit }
}
