import { randomBytes, randomUUID } from 'node:crypto'
import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { bridgeDirectory, bridgeError, dshSessionId, endpointFile, maxRequestBytes, readLine, requestPrefix, requestUuid, sameToken, socketTimeoutMs } from './protocol.js'
import { createTasks } from './tasks.js'
import { createDirectChat } from './direct-chat.js'
import { attachmentSources, codexAttachment, importAttachment, readAttachments } from './attachments.js'

export const inject = ['connection', 'typertGateway', 'tools']
const taskOperations = new Set(['submit', 'status', 'wait', 'review'])
const writeOperations = new Set(['send', 'submit', 'review'])

export async function apply(ctx) {
  const peer = ctx.connection.createPeer({ principal: { kind: 'owner' }, interactions: 'none' })
  const gateway = ctx.typertGateway
  const directory = bridgeDirectory()
  const endpoint = endpointFile(directory)
  const pipe = '\\\\.\\pipe\\dsh-codex-' + randomUUID()
  const token = randomBytes(32).toString('hex')
  const temporary = endpoint + '.' + randomUUID()
  const sockets = new Set()
  const writes = new Map()
  const tasks = createTasks(ctx, directory, visibleText)

  const invoke = (method, args, signal) =>
    gateway.invoke({ namespace: 'session', method, args, peer, signal })
  const directChat = createDirectChat(ctx, undefined, (session, id, seq, signal) =>
    codexAttachment(ctx, session, id, seq, (method, args) => invoke(method, args, signal)))

  const server = createServer(socket => {
    sockets.add(socket)
    const connection = new AbortController()
    const signal = AbortSignal.any([connection.signal, peer.signal])
    socket.setTimeout(socketTimeoutMs, () => socket.destroy())
    socket.on('error', () => socket.destroy())
    socket.on('close', () => {
      sockets.delete(socket)
      connection.abort()
    })
    const respond = response => {
      if (!socket.destroyed) socket.end(JSON.stringify(response) + '\n')
    }
    const reject = error => respond({
      ok: false,
      code: error.code || 'bridge-error',
      message: error.message || 'DSH could not complete the bridge request.',
    })
    readLine(socket, maxRequestBytes, async line => {
      try {
        const request = JSON.parse(line)
        if (!sameToken(request?.token, token)) throw bridgeError('unauthorized', 'Invalid local bridge token.')
        const call = (method, args) => invoke(method, args, signal)
        const handle = () => {
          if (request.op === 'send') return directChat.submit(request,
            payload => dispatch(payload, call, path => importAttachment(ctx, path, request.sessionId, signal)))
          if (['attachments', 'attachment-bytes', 'attachment-data'].includes(request.op)) {
            return readAttachments(ctx, requireSessionId(request.sessionId), request, call)
          }
          if (request.op === 'task-current') {
            return tasks.summary(requireSessionId(request.sessionId), call)
          }
          if (taskOperations.has(request.op)) {
            return tasks.handle(requireSessionId(request.sessionId), request, call, signal)
          }
          return dispatch(request, call)
        }
        const value = writeOperations.has(request.op)
          ? await serializeWrite(writes, requireSessionId(request.sessionId), signal, handle)
          : await handle()
        respond({ ok: true, value })
      } catch (error) {
        reject(error)
      }
    }, reject)
  })

  ctx.effect(() => () => {
    for (const socket of sockets) socket.destroy()
    server.close()
    rmSync(temporary, { force: true })
    try {
      if (JSON.parse(readFileSync(endpoint, 'utf8')).pipe === pipe) rmSync(endpoint)
    } catch (error) {
      if (error.code !== 'ENOENT') ctx.logger('codex-bridge').warn('Could not remove the bridge endpoint: %s', error.message)
    }
  })

  mkdirSync(directory, { recursive: true, mode: 0o700 })
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(pipe, () => {
      server.off('error', reject)
      server.on('error', error => ctx.logger('codex-bridge').error(error))
      resolve()
    })
  })
  peer.signal.throwIfAborted()
  writeFileSync(temporary, JSON.stringify({ version: 1, pipe, token }), { flag: 'wx', mode: 0o600 })
  renameSync(temporary, endpoint)
}

async function serializeWrite(writes, sessionId, signal, send) {
  const previous = writes.get(sessionId) ?? Promise.resolve()
  const current = previous.catch(() => {}).then(() => {
    signal.throwIfAborted()
    return send()
  })
  writes.set(sessionId, current)
  try {
    return await current
  } finally {
    if (writes.get(sessionId) === current) writes.delete(sessionId)
  }
}

function requireSessionId(value) {
  if (typeof value !== 'string' || !dshSessionId.test(value)) {
    throw bridgeError('session-required', 'Choose a session ID from the list command.')
  }
  return value
}

function humanMessage(event) {
  return event.type === 'user/message' && event.surfaceOp === 'append' && event.data?.source?.kind === 'user'
}

export function visibleText(event) {
  if (!humanMessage(event) && event.type !== 'assistant/message') return ''
  const content = event.data?.message?.content ?? event.data?.content
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return ''
  return content.filter(part => part?.type === 'text' && typeof part.text === 'string').map(part => part.text).join('')
}

function textChunk(text, offset) {
  let end = Math.min(offset + 24_000, text.length)
  const last = text.charCodeAt(end - 1)
  if (end < text.length && last >= 0xd800 && last <= 0xdbff) end--
  return { offset, text: text.slice(offset, end),
    ...(end < text.length ? { truncated: true, nextOffset: end } : {}) }
}

function messageChunk(event, offset = 0) {
  const text = visibleText(event)
  if (!text || offset >= text.length) return undefined
  const fromCodex = humanMessage(event) && event.data.source.rpcId?.startsWith(requestPrefix)
  const role = fromCodex ? 'codex' : humanMessage(event) ? 'user' : 'deepseek'
  return { seq: event.seq, role, ...textChunk(text, offset) }
}

function toolNames(records) {
  return new Map(records.flatMap(({ event }) => event.type === 'tool/call' && event.data?.callId
    ? [[event.data.callId, event.data.name]] : []))
}

function toolSummary(event, names) {
  if (event.type !== 'tool/result' || !event.data?.message) return undefined
  const { message, turn, step } = event.data
  const { error, meta } = event.data
  return { seq: event.seq, turn, step, tool: names.get(message.toolCallId) ?? message.name,
    callId: message.toolCallId, isError: !!message.isError || !!error,
    ...(typeof error?.code === 'string' ? { errorCode: error.code } : {}),
    ...(Number.isInteger(meta?.exitCode) ? { exitCode: meta.exitCode } : {}) }
}

export async function dispatch(request, invoke, importFile) {
  if (request.op === 'list') {
    const { items } = await invoke('list', { _request: {} })
    return items.filter(item => !item.parentSessionId && item.origin !== 'subagent')
      .map(({ sessionId, projections, cwd, running, blank, updatedAt }) =>
        ({ sessionId, title: projections?.values?.title ?? null, cwd, running, blank, updatedAt }))
      .filter(item => request.title === undefined || request.title === item.title)
  }

  const sessionId = requireSessionId(request.sessionId)
  switch (request.op) {
    case 'history': {
      const { limit = 30, beforeSeq } = request
      if (!Number.isInteger(limit) || limit < 1 || limit > 50 ||
          (beforeSeq !== undefined && (!Number.isSafeInteger(beforeSeq) || beforeSeq < 0))) {
        throw bridgeError('invalid-page', 'History requires a limit of 1–50 and an optional non-negative cursor.')
      }
      const page = await invoke('events', { request: {
        address: { kind: 'session', sessionId },
        maxMessages: limit,
        ...(beforeSeq === undefined ? {} : { beforeSeq }),
      } })
      const names = toolNames(page.records)
      return {
        sessionId,
        cursor: page.cursor,
        beforeSeq: page.records[0]?.event.seq,
        hasMore: page.hasMore,
        messages: page.records.flatMap(({ event }) => messageChunk(event) ?? []),
        attachments: page.records.flatMap(({ event }) => attachmentSources(event)),
        toolResults: page.records.flatMap(({ event }) => toolSummary(event, names) ?? []),
      }
    }
    case 'message':
    case 'tool-result': {
      const { seq, offset = 0 } = request
      if (![seq, offset].every(value => Number.isSafeInteger(value) && value >= 0)) {
        throw bridgeError('invalid-message-range', 'Provide a message sequence and optional text offset.')
      }
      const page = await invoke('events', { request: {
        address: { kind: 'session', sessionId }, throughSeq: seq, maxMessages: request.op === 'tool-result' ? 20 : 1,
      } })
      const event = page.records.find(item => item.event.seq === seq)?.event
      if (request.op === 'tool-result') {
        const summary = event && toolSummary(event, toolNames(page.records))
        if (!summary) throw bridgeError('tool-result-not-found', 'No recorded tool result exists at that message sequence.')
        const content = event.data.message.content
        const text = Array.isArray(content) ? content
          .filter(part => part?.type === 'text' && typeof part.text === 'string')
          .map(part => part.text).join('\n') : typeof content === 'string' ? content : ''
        if (offset > text.length || (offset === text.length && offset > 0)) {
          throw bridgeError('invalid-message-range', 'The offset is outside the tool result.')
        }
        return { sessionId, ...summary, ...textChunk(text, offset), attachments: attachmentSources(event) }
      }
      const chunk = event && messageChunk(event, offset)
      if (!chunk) throw bridgeError('message-not-found', 'No visible text at that sequence and offset.')
      return { sessionId, ...chunk }
    }
    case 'state': {
      const { cursor, running, pendingInput } = await invoke('state', { request: { sessionId } })
      return { sessionId, cursor, running, pendingInput }
    }
    case 'send': {
      const { text, requestId, filePath } = request
      if (typeof text !== 'string' || !text.trim() || text.length > 12_000) {
        throw bridgeError('invalid-text', 'Send 1–12,000 characters of text.')
      }
      if (typeof requestId !== 'string' || !requestUuid.test(requestId)) {
        throw bridgeError('request-id-required', 'Send requires a UUID to make retries safe.')
      }
      const content = [{ type: 'text', text: '【Codex】' + text.trim() }]
      if (filePath !== undefined) content.push(await importFile(filePath))
      return invoke('prompt', { request: {
        sessionId, requestId: requestPrefix + requestId.toLowerCase(), mode: 'steer',
        content,
      } })
    }
    default:
      throw bridgeError('unknown-operation', 'Unknown chat or task operation.')
  }
}
