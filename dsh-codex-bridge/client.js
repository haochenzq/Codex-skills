import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createConnection } from 'node:net'
import { bridgeDirectory, bridgeError, endpointFile, maxResponseBytes, readLine, socketTimeoutMs } from './protocol.js'

async function call(request) {
  const endpoint = await readFile(endpointFile(bridgeDirectory()), 'utf8').then(JSON.parse).catch(error => {
    if (error.code === 'ENOENT') throw bridgeError('bridge-offline', 'Open DeepSeek Harness and enable the Codex chat bridge.')
    throw error
  })
  if (endpoint.version !== 1 || !/^\\\\\.\\pipe\\dsh-codex-[a-f0-9-]{36}$/i.test(endpoint.pipe) ||
      !/^[a-f0-9]{64}$/.test(endpoint.token)) {
    throw bridgeError('invalid-endpoint', 'The local DSH bridge endpoint is invalid.')
  }
  return new Promise((resolve, reject) => {
    const socket = createConnection(endpoint.pipe)
    socket.setTimeout(socketTimeoutMs, () => socket.destroy(bridgeError('timeout', 'DSH bridge timed out.')))
    socket.once('error', reject)
    socket.once('close', () => reject(bridgeError('connection-closed', 'DSH bridge closed before replying.')))
    socket.once('connect', () => socket.write(JSON.stringify({
      ...request, codexThreadId: process.env.CODEX_THREAD_ID, token: endpoint.token,
    }) + '\n'))
    readLine(socket, request.op === 'attachment-data' ? 24 * 1024 * 1024 : maxResponseBytes, line => {
      try {
        const response = JSON.parse(line)
        if (!response.ok) throw bridgeError(response.code, response.message)
        resolve(response.value)
      } catch (error) {
        reject(error)
      } finally {
        socket.destroy()
      }
    }, error => socket.destroy(error))
  })
}

async function exportAttachment(sessionId, seq, attachmentId, destination) {
  if (!destination) throw bridgeError('destination-required', 'Choose a destination file.')
  if (!/^sha256:[a-f0-9]{64}$/.test(attachmentId)) throw bridgeError('invalid-attachment', 'Provide the original attachment digest.')
  const sha256 = attachmentId.slice(7)
  const attachment = await call({ op: 'attachment-data', sessionId, seq, attachmentId })
  const result = Buffer.from(attachment.data, 'base64')
  if (attachment.sha256 !== sha256 || result.length !== attachment.total ||
      createHash('sha256').update(result).digest('hex') !== sha256) {
    throw bridgeError('attachment-integrity', 'Export did not match the original attachment digest.')
  }
  const path = resolve(destination)
  await writeFile(path, result, { flag: 'wx' })
  return { path, sha256, bytes: result.length, mediaType: attachment.mediaType ?? 'application/octet-stream' }
}

async function readJson(path) {
  return JSON.parse((await readFile(path, 'utf8')).replace(/^\uFEFF/, ''))
}

const usage = [
  'node client.js list [exact title]',
  'node client.js history <sessionId> [limit] [beforeSeq]',
  'node client.js message <sessionId> <seq> [offset]',
  'node client.js tool-result <sessionId> <seq> [offset]',
  'node client.js state <sessionId>',
  'node client.js attachments <sessionId> [beforeSeq]',
  'node client.js attachment-export <sessionId> <seq> <sha256:...> <destination>',
  'node client.js send <sessionId> <requestUuid> [--reply-to <codexId>] <text>',
  'node client.js send-file <sessionId> <requestUuid> <path> [--reply-to <codexId>] <text>',
  'node client.js submit <sessionId> <taskUuid> <task.json>',
  'node client.js status <sessionId> <taskUuid>',
  'node client.js wait <sessionId> <taskUuid> [seconds, 1–10]',
  'node client.js review <sessionId> <taskUuid> <accept|reject> <evidence>',
  'node client.js task-current <sessionId>',
].join('\n')

const [op, sessionId, first, second, ...rest] = process.argv.slice(2)
try {
  if (!op || op === '--help') {
    console.log(usage)
  } else if (op === 'attachment-export') {
    console.log(JSON.stringify(await exportAttachment(sessionId, Number(first), second, rest[0]), null, 2))
  } else {
    const request = { op, sessionId }
    if (op === 'list' && sessionId !== undefined) {
      request.title = [sessionId, first, second, ...rest].filter(value => value !== undefined).join(' ')
    }
    if (op === 'history') {
      if (first !== undefined) request.limit = Number(first)
      if (second !== undefined) request.beforeSeq = Number(second)
    }
    if (op === 'message' || op === 'tool-result') {
      request.seq = Number(first)
      if (second !== undefined) request.offset = Number(second)
    }
    if (op === 'send' || op === 'send-file') {
      request.op = 'send'
      request.requestId = first
      const parts = op === 'send-file' ? [...rest] : [second, ...rest]
      if (parts[0] === '--reply-to') {
        parts.shift()
        request.replyTo = parts.shift()
        if (!request.replyTo) throw bridgeError('invalid-reply-target', 'Choose an existing Codex chat link or ID.')
      }
      request.text = parts.join(' ')
      if (op === 'send-file') {
        if (!second) throw bridgeError('invalid-attachment', 'Choose an attachment path.')
        request.filePath = resolve(second)
      }
    }
    if (['submit', 'status', 'wait', 'review'].includes(op)) request.taskId = first
    if (op === 'submit') request.task = await readJson(second)
    if (op === 'wait' && second !== undefined) request.seconds = Number(second)
    if (op === 'review') {
      request.decision = second
      request.evidence = rest.join(' ')
    }
    if (op === 'attachments' && first !== undefined) request.beforeSeq = Number(first)
    console.log(JSON.stringify(await call(request), null, 2))
  }
} catch (error) {
  console.error(JSON.stringify({ code: error.code || 'bridge-error', message: error.message }))
  process.exitCode = 1
}
