import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { bridgeError, dshSessionId, requestPrefix, requestUuid } from './protocol.js'
import { connectCodexService, withCodexService } from './codex-service.js'
import { sendThroughDesktop, subagentTargetError } from './codex-desktop.js'

const originLifetime = 30 * 60 * 1000

function threadId(value) {
  if (typeof value !== 'string') return null
  const id = value.trim().replace(/^codex:\/\/threads\//i, '')
  return requestUuid.test(id) ? id.toLowerCase() : null
}

function isAutomaticTarget(target) {
  return target === undefined || (typeof target === 'string' && !target.trim())
}

function currentTurn(session) {
  const pages = []
  for (let end = session.seq; end > 0;) {
    const offset = Math.max(0, end - 500)
    const events = session.snapshotEvents(offset, end)
    const boundary = events.findLastIndex(event => event.type === 'turn/start' || event.type === 'turn/end')
    if (boundary >= 0) {
      if (events[boundary].type !== 'turn/start') return undefined
      pages.push(events.slice(boundary + 1))
      return { seq: events[boundary].seq, events: pages.reverse().flat() }
    }
    pages.push(events)
    end = offset
  }
}

function codexCli() {
  const home = process.env.CODEX_HOME || join(homedir(), '.codex')
  const managed = join(home, 'packages', 'app-server-daemon', 'current', 'bin', 'codex.exe')
  return existsSync(managed) ? managed : 'codex.exe'
}

export async function resolveMainCodexThread(target, connect = connectCodexService) {
  return connect(codexCli(), async rpc => {
    const seen = new Set()
    let current = target
    while (!seen.has(current)) {
      seen.add(current)
      const { thread } = await rpc('thread/read', { threadId: current, includeTurns: false })
      if (thread?.id !== current || !thread.source) return target
      if (!thread.source.subAgent) return current
      const parent = threadId(thread.source.subAgent.thread_spawn?.parent_thread_id)
      if (!parent) return target
      current = parent
    }
    return target
  }, 3_000).catch(() => target)
}

export async function sendCodexMessage(target, message, attachment, connect = withCodexService, desktop = sendThroughDesktop) {
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
  let result
  try {
    result = await desktop(request)
  } catch (error) {
    if (error.code !== 'codex-desktop-unavailable') throw error
    result = null
  }
  if (result === null) {
    const queued = await connect(codexCli(), async rpc => {
      const { thread } = await rpc('thread/read', { threadId: target, includeTurns: false })
      if (thread.source?.subAgent) throw subagentTargetError()
      return rpc('thread/queue/add', request)
    })
    const submission = queued?.queuedSubmission
    if (!submission?.id || submission.clientUserMessageId !== messageId) {
      throw bridgeError('codex-delivery-unknown', 'Codex did not confirm this queue entry. Check the target before retrying.')
    }
    return { status: 'queued', messageId, queueId: submission.id,
      ...(attachment ? { attachment: attachment.kind === 'image' ? 'image' : 'file-reference' } : {}) }
  }
  const { turn } = result
  if (!turn?.id) throw bridgeError('codex-delivery-unknown', 'Codex did not return a turn receipt. Check the target before retrying.')
  return { messageId, turnId: turn.id, status: 'sent',
    ...(attachment ? { attachment: attachment.kind === 'image' ? 'image' : 'file-reference' } : {}) }
}

export function createDirectChat(ctx, directory, send, findAttachment,
  resolveMain = resolveMainCodexThread) {
  const origins = new Map()
  const sent = new Map()
  const routeDirectory = join(directory, 'codex-routes')
  const routeFile = sessionId => join(routeDirectory, sessionId + '.json')

  function loadRoutes(sessionId) {
    let entries
    try {
      entries = JSON.parse(readFileSync(routeFile(sessionId), 'utf8'))
    } catch (error) {
      if (error.code === 'ENOENT') return new Set()
      throw bridgeError('codex-routes-unavailable', 'Could not read this DSH chat’s saved Codex destinations.')
    }
    if (!Array.isArray(entries) || entries.some(entry => !threadId(entry))) {
      throw bridgeError('codex-routes-unavailable', 'This DSH chat’s saved Codex destinations are invalid.')
    }
    return new Set(entries.map(threadId))
  }

  function rememberRoute(sessionId, target) {
    const routes = loadRoutes(sessionId)
    if (routes.has(target)) return
    routes.add(target)
    mkdirSync(routeDirectory, { recursive: true, mode: 0o700 })
    const file = routeFile(sessionId)
    const temporary = file + '.' + randomUUID()
    try {
      writeFileSync(temporary, JSON.stringify([...routes]), { flag: 'wx', mode: 0o600 })
      renameSync(temporary, file)
    } finally {
      rmSync(temporary, { force: true })
    }
  }

  function rememberAcceptedRoute(sessionId, target) {
    try {
      rememberRoute(sessionId, target)
    } catch (error) {
      ctx.logger?.('codex-bridge').warn('Could not save the Codex chat pairing: %s', error.message)
    }
  }

  async function chooseTarget(target, choices, sessionId) {
    const automatic = isAutomaticTarget(target)
    const requested = automatic ? undefined : threadId(target)
    if (automatic && choices.size === 1) return choices.values().next().value
    if (choices.has(requested)) return requested
    if (!automatic || choices.size === 0) {
      const saved = loadRoutes(sessionId)
      const routes = automatic ? new Set(await Promise.all([...saved].map(id => resolveMain(id)))) : saved
      if (routes.has(requested)) return requested
      if (automatic && routes.size === 1) return routes.values().next().value
      if (automatic && routes.size > 1) {
        throw bridgeError('codex-target-not-authorized', 'This DSH chat has several paired Codex chats. Specify one paired link or UUID.')
      }
    }
    if (automatic && choices.size > 1) {
      throw bridgeError('codex-target-not-authorized', 'Several Codex chats were selected in this turn. Specify which one to contact.')
    }
    throw bridgeError('codex-target-not-authorized', 'Use a Codex chat authorized in this turn or previously paired with this DSH chat. A Codex chat pairs when it sends a message accepted here.')
  }

  ctx.tools.register({
    name: 'send_to_codex',
    description: 'Send a 【DSH】 message to an existing Codex chat. Omit target to use the sole Codex chat authorized in this turn, or the sole paired Codex chat when this turn has no destination. If several chats are paired, provide the intended paired Codex link or UUID as target. During an authorized joint task, proactively send evidence, a decision needed to unblock work, or a verified completion. Include the task and next action if there is one. Stop when the agreed work is complete and skip acknowledgments. Only send attachments authorized for sharing from this DSH chat. Native images stay images, other files use verified local references. Never invent an attachmentId or sourceSeq. If delivery status is unknown, check the target before retrying.',
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
    description: 'Send plain text to the sole Codex chat authorized in this DSH turn, or proactively contact the sole paired Codex chat when this turn has no destination. Provide only the message. If there are several paired chats, use send_to_codex with the intended paired link or UUID. Use this for a completed handoff, an evidence request, or a concrete blocker.',
    parameters: {
      type: 'object', additionalProperties: false, required: ['message'],
      properties: { message: { type: 'string', minLength: 1, maxLength: 4000 } },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    execute({ message }, exec) {
      return deliver({ message }, exec)
    },
  })

  ctx.tools.register({
    name: 'send_text_to_codex',
    description: 'Proactively send plain text to one authorized Codex chat by its exact UUID or link. With multiple paired chats, select the intended target on each call.',
    parameters: {
      type: 'object', additionalProperties: false, required: ['target', 'message'],
      properties: {
        target: { type: 'string', minLength: 1 },
        message: { type: 'string', minLength: 1, maxLength: 4000 },
      },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    execute({ target, message }, exec) {
      if (!threadId(target)) throw bridgeError('invalid-reply-target', 'Choose a Codex chat link or UUID.')
      return deliver({ target, message }, exec)
    },
  })

  ctx.tools.register({
    name: 'send_to_active_codex',
    description: 'Deliver text exclusively to the current running turn in one paired Codex chat. Specify its exact UUID or link. The receiving turn handles the text at its next tool or completion boundary. If unavailable, report the failure without queueing or resending.',
    parameters: {
      type: 'object', additionalProperties: false, required: ['target', 'message'],
      properties: { target: { type: 'string', minLength: 1 }, message: { type: 'string', minLength: 1, maxLength: 4000 } },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    execute({ target, message }, exec) {
      if (!threadId(target)) throw bridgeError('invalid-reply-target', 'Choose a Codex chat link or UUID.')
      return deliver({ target, message, activeOnly: true }, exec)
    },
  })

  async function deliver({ target, message, attachmentId, sourceSeq, activeOnly = false }, exec) {
    const session = exec.agent?.session
    if (!dshSessionId.test(session?.id) || typeof message !== 'string' || !message.trim() || message.length > 4000) {
      throw bridgeError('invalid-codex-message', 'A message requires 1–4,000 characters in a DSH conversation.')
    }
    const turn = currentTurn(session)
    if (!turn) {
      throw bridgeError('codex-target-not-authorized', 'Send from an active DSH turn.')
    }
    const choices = new Set()
    const humanChoices = new Set()
    for (const event of turn.events) {
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
      if (targets.size === 1) {
        const selected = targets.values().next().value
        humanChoices.add(selected)
        choices.add(selected)
      }
    }
    const requested = await chooseTarget(target, choices, session.id)
    if ((!isAutomaticTarget(target) || humanChoices.has(requested)) &&
      await resolveMain(requested) !== requested) throw subagentTargetError()
    const body = message.trim()
    const key = JSON.stringify([session.id, turn.seq, requested, body, attachmentId, sourceSeq, activeOnly])
    const now = Date.now()
    for (const [oldKey, entry] of sent) {
      if (entry.expiresAt <= now) sent.delete(oldKey)
    }
    let delivery = sent.get(key)
    if (!delivery) {
      delivery = { result: (async () => {
        const attachment = attachmentId === undefined ? undefined
          : await findAttachment(session, attachmentId, sourceSeq, exec.signal)
        const receipt = await send(requested, body, attachment, activeOnly)
        if (['sent', 'queued', 'hook-delivered'].includes(receipt?.status) && humanChoices.has(requested)) rememberAcceptedRoute(session.id, requested)
        return receipt
      })(), expiresAt: now + originLifetime }
      sent.set(key, delivery)
    }
    return JSON.stringify(await delivery.result)
  }

  async function submit(request, dispatch) {
    const source = threadId(request.codexThreadId)
    const target = request.replyTo === undefined && source ? await resolveMain(source) : threadId(request.replyTo)
    if (request.replyTo !== undefined && !target) {
      throw bridgeError('invalid-reply-target', 'Choose an existing Codex chat link or ID.')
    }
    if (request.replyTo !== undefined && await resolveMain(target) !== target) {
      throw subagentTargetError()
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
    const result = await dispatch(request)
    if (result?.accepted === true && target && (request.replyTo === undefined || source === target) &&
      dshSessionId.test(request.sessionId)) {
      rememberAcceptedRoute(request.sessionId, target)
    }
    return result
  }

  return { submit }
}
