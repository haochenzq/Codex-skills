import { timingSafeEqual } from 'node:crypto'
import { join } from 'node:path'

export const endpointFile = directory => join(directory, 'endpoint.json')
export const bridgeDirectory = () =>
  process.env.DSH_CODEX_BRIDGE_DIR || join(process.env.LOCALAPPDATA, 'DSH Codex Bridge')

export const maxRequestBytes = 64 * 1024
export const maxResponseBytes = 8 * 1024 * 1024
export const socketTimeoutMs = 15_000
export const requestUuid = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i
export const dshSessionId = /^session-[A-Za-z0-9_-]{1,128}$/
export const requestPrefix = 'codex-bridge:'
export const taskPrefix = requestPrefix + 'task:'

export function sameToken(candidate, expected) {
  if (typeof candidate !== 'string' || !/^[a-f0-9]{64}$/.test(candidate)) return false
  return timingSafeEqual(Buffer.from(candidate, 'hex'), Buffer.from(expected, 'hex'))
}

export function bridgeError(code, message) {
  return Object.assign(new Error(message), { code })
}

export function readLine(socket, limit, receive, fail) {
  const chunks = []
  let size = 0
  function onData(chunk) {
    const newline = chunk.indexOf(10)
    const line = newline < 0 ? chunk : chunk.subarray(0, newline)
    size += line.length
    if (size > limit) {
      socket.off('data', onData)
      fail(bridgeError('frame-too-large', 'Message exceeds the local bridge limit.'))
      return
    }
    chunks.push(line)
    if (newline >= 0) {
      socket.off('data', onData)
      receive(Buffer.concat(chunks, size).toString('utf8'))
    }
  }
  socket.on('data', onData)
}
