import { randomUUID } from 'node:crypto'
import { createConnection } from 'node:net'
import { bridgeError } from './protocol.js'

const pipe = '\\\\.\\pipe\\codex-ipc'
const maxFrameBytes = 32 * 1024 * 1024

// Use the same owner discovery and follower delivery protocol as Codex desktop.
export async function sendThroughDesktop(request) {
  const socket = createConnection(pipe)
  let clientId = 'uninitialized'
  let pending
  let buffer = Buffer.alloc(0)
  let submitted = false
  const failure = () => submitted
    ? bridgeError('codex-delivery-unknown', 'Codex desktop did not confirm delivery. Check the target before retrying.')
    : bridgeError('codex-desktop-unavailable', 'Could not resolve the target through Codex desktop.')
  socket.on('error', () => pending?.reject(failure()))
  socket.on('close', () => pending?.reject(failure()))
  socket.on('data', data => {
    buffer = Buffer.concat([buffer, data])
    while (buffer.length >= 4) {
      const size = buffer.readUInt32LE(0)
      if (size > maxFrameBytes) { socket.destroy(); return }
      if (buffer.length < size + 4) return
      let response
      try { response = JSON.parse(buffer.subarray(4, size + 4)) } catch { socket.destroy(); return }
      buffer = buffer.subarray(size + 4)
      if (response?.type === 'response' && response.requestId === pending?.id) pending.resolve(response)
    }
  })

  async function call(method, version, params, targetClientId, timeoutMs = 12_000) {
    const id = randomUUID()
    const payload = Buffer.from(JSON.stringify({ type: 'request', requestId: id, method, version,
      params, targetClientId, timeoutMs, sourceClientId: clientId }))
    const header = Buffer.alloc(4)
    header.writeUInt32LE(payload.length)
    let timer
    try {
      return await new Promise((resolve, reject) => {
        pending = { id, resolve, reject }
        timer = setTimeout(() => reject(failure()), timeoutMs + 250)
        socket.write(Buffer.concat([header, payload]), error => { if (error) reject(failure()) })
      })
    } finally {
      pending = undefined
      clearTimeout(timer)
    }
  }

  try {
    const connected = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => { socket.destroy(); reject(failure()) }, 2_000)
      socket.once('connect', () => { clearTimeout(timer); resolve(true) })
      socket.once('error', error => {
        clearTimeout(timer)
        if (['ENOENT', 'ECONNREFUSED'].includes(error.code)) resolve(false)
        else reject(failure())
      })
    })
    if (!connected) return null
    const initialized = await call('initialize', 0, { clientType: 'dsh-codex-bridge' })
    clientId = initialized.result?.clientId
    if (initialized.resultType !== 'success' || !clientId) throw failure()
    const owner = await call('thread-owner-discovery', 1, { hostId: 'local', conversationId: request.threadId })
    if (owner.resultType === 'error' && owner.error === 'no-client-found') return null
    if (owner.resultType !== 'success' || !owner.handledByClientId || !owner.result?.supportsUntrustedAppInput) throw failure()

    submitted = true
    const response = await call('thread-follower-start-turn', 2, {
      conversationId: request.threadId,
      turnStart: { request, context: { inheritThreadSettings: true } },
    }, owner.handledByClientId)
    if (response.resultType !== 'success' || response.handledByClientId !== owner.handledByClientId) throw failure()
    return response.result?.result ?? {}
  } finally {
    socket.destroy()
  }
}
