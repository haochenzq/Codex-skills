import { execFile, spawn } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { createServer } from 'node:net'
import { once } from 'node:events'
import { promisify } from 'node:util'
import { bridgeError } from './protocol.js'

const runFile = promisify(execFile)

export async function withCodexService(cli, run, connect = connectCodexService, start = startCodexDaemon) {
  try {
    return await connect(cli, run)
  } catch (error) {
    if (error.code !== 'codex-control-unreachable') throw error
  }
  try {
    await start(cli)
  } catch {
    throw bridgeError('codex-unavailable', 'Could not start the local Codex service. The message was not sent.')
  }
  return connect(cli, run)
}

function startCodexDaemon(cli) {
  return runFile(cli, ['app-server', 'daemon', 'start'], {
    windowsHide: true, timeout: 15_000, maxBuffer: 64 * 1024,
  })
}

// The Windows CLI proxies its private control socket as a raw WebSocket stream.
// Keep the TCP adapter one-shot, loopback-only and protected by a random URL.
export async function connectCodexService(cli, run) {
  const path = '/' + randomUUID()
  const clients = new Set()
  let proxy
  let ws
  let timer
  let connectionError
  let sendStarted = false
  const server = createServer(socket => {
    clients.add(socket)
    socket.on('close', () => clients.delete(socket))
    socket.on('error', () => socket.destroy())
    socket.setTimeout(3000, () => socket.destroy())
    let headers = Buffer.alloc(0)
    function admit(data) {
      headers = Buffer.concat([headers, data])
      if (headers.length > 8192) return socket.destroy()
      const end = headers.indexOf('\r\n\r\n')
      if (end < 0) return
      const lineEnd = headers.indexOf('\r\n')
      if (proxy || headers.subarray(0, lineEnd).toString() !== 'GET ' + path + ' HTTP/1.1') return socket.destroy()
      socket.off('data', admit)
      socket.setTimeout(0)
      server.close()
      proxy = spawn(cli, ['app-server', 'proxy'], { windowsHide: true, stdio: ['pipe', 'pipe', 'ignore'] })
      proxy.on('error', error => { connectionError = error; socket.destroy() })
      proxy.stdin.on('error', () => socket.destroy())
      proxy.on('exit', () => socket.destroy())
      proxy.stdin.write(Buffer.concat([Buffer.from('GET / HTTP/1.1'), headers.subarray(lineEnd)]))
      socket.pipe(proxy.stdin)
      proxy.stdout.pipe(socket)
    }
    socket.on('data', admit)
  })
  server.listen(0, '127.0.0.1')
  try {
    await once(server, 'listening')
    ws = new WebSocket('ws://127.0.0.1:' + server.address().port + path)
    const pending = new Map()
    let id = 0
    function closed() {
      for (const { reject } of pending.values()) reject(connectionError ||
        bridgeError('codex-delivery-unknown', 'Codex closed the connection. Check the target before retrying.'))
      pending.clear()
    }
    ws.addEventListener('close', closed)
    ws.addEventListener('message', ({ data }) => {
      let response
      try { response = JSON.parse(data) } catch { return }
      const call = pending.get(response.id)
      if (!call) return
      pending.delete(response.id)
      if (response.error) call.reject(bridgeError('codex-request-rejected', response.error.message))
      else call.resolve(response.result)
    })
    const operation = async () => {
      await new Promise((resolve, reject) => {
        ws.addEventListener('open', resolve, { once: true })
        ws.addEventListener('error', () => reject(connectionError ||
          bridgeError('codex-control-unreachable', 'Cannot connect to the local Codex service. The message was not sent.')), { once: true })
      })
      function rpc(method, params) {
        if (ws.readyState !== WebSocket.OPEN) throw bridgeError('codex-unavailable', 'Local Codex service disconnected.')
        const key = ++id
        return new Promise((resolve, reject) => {
          pending.set(key, { resolve, reject })
          const payload = JSON.stringify({ id: key, method, params })
          if (method === 'turn/start') sendStarted = true
          ws.send(payload)
        })
      }
      await rpc('initialize', { clientInfo: { name: 'dsh-codex-bridge', version: '0.6.6' },
        capabilities: { experimentalApi: true } })
      ws.send(JSON.stringify({ method: 'initialized', params: {} }))
      return run(rpc)
    }
    return await Promise.race([operation(), new Promise((_, reject) => {
      timer = setTimeout(() => reject(sendStarted
        ? bridgeError('codex-delivery-unknown', 'Codex timed out. Check the target before retrying.')
        : bridgeError('codex-control-timeout', 'Codex timed out before sending the message.')), 20_000)
    })])
  } finally {
    clearTimeout(timer)
    if (ws?.readyState === WebSocket.OPEN) ws.close()
    for (const socket of clients) socket.destroy()
    proxy?.kill()
    if (server.listening) server.close()
  }
}
