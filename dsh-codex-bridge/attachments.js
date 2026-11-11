import { createHash } from 'node:crypto'
import { open } from 'node:fs/promises'
import { basename, extname, isAbsolute } from 'node:path'
import { bridgeError } from './protocol.js'

const digestId = /^sha256:([a-f0-9]{64})$/
export const attachmentLimit = 16 * 1024 * 1024
const chunkSize = 1024 * 1024
const imageTypes = new Map([['.png', 'image/png'], ['.jpg', 'image/jpeg'], ['.jpeg', 'image/jpeg'],
  ['.webp', 'image/webp'], ['.gif', 'image/gif']])

export function attachmentSources(event) {
  const data = event.data
  if (!['tool/result', 'user/message', 'assistant/message'].includes(event.type) || data.message?.isError) return []
  if (event.type === 'user/message' && data.source?.kind !== 'user') return []
  const content = data.message?.content ?? data.content
  if (!Array.isArray(content)) return []
  return content.flatMap(part => {
    if (!['image', 'file'].includes(part?.type)) return []
    const attachment = part.attachment
    if (!digestId.test(attachment?.attachmentId) || !Number.isSafeInteger(attachment.bytes) ||
        attachment.bytes < 0 || attachment.bytes > attachmentLimit) return []
    return [{ seq: event.seq, kind: part.type, attachment }]
  })
}

export async function readAttachments(ctx, sessionId, request, invoke) {
  const address = { kind: 'session', sessionId }
  if (request.op === 'attachments') {
    const { beforeSeq } = request
    if (beforeSeq !== undefined && (!Number.isSafeInteger(beforeSeq) || beforeSeq < 0)) {
      throw bridgeError('invalid-page', 'Choose a valid history cursor.')
    }
    const page = await invoke('events', { request: { address, maxMessages: 40,
      ...(beforeSeq === undefined ? {} : { beforeSeq }) } })
    return { sources: page.records.flatMap(({ event }) => attachmentSources(event)).reverse(),
      beforeSeq: page.hasMore ? page.records[0]?.event.seq ?? null : null }
  }
  const { seq, attachmentId, offset = 0 } = request
  if (!Number.isSafeInteger(seq) || seq < 0 || !digestId.test(attachmentId) ||
      !Number.isSafeInteger(offset) || offset < 0) {
    throw bridgeError('invalid-attachment', 'Choose the exact source message, attachment digest and byte offset.')
  }
  const page = await invoke('events', { request: { address, throughSeq: seq, maxMessages: 1 } })
  const event = page.records.find(row => row.event.seq === seq)?.event
  const source = event && attachmentSources(event).find(item => item.attachment.attachmentId === attachmentId)
  if (!source) throw bridgeError('attachment-not-in-session', 'The selected attachment is not present in that message.')
  const { attachment, kind } = source
  if (offset !== 0 && offset >= attachment.bytes) throw bridgeError('invalid-offset', 'Offset is outside the attachment.')
  let bytes
  if (kind === 'image') {
    const result = await invoke('attachment', { request: { sessionId, attachment } })
    bytes = Buffer.from(result.data, 'base64')
  } else {
    const store = ctx.get('attachments')
    if (!store) throw bridgeError('attachment-unavailable', 'The DSH attachment store is unavailable.')
    const chunks = []
    let length = 0
    for await (const chunk of store.readFileStream(attachment)) {
      length += chunk.byteLength
      if (length > attachment.bytes) throw bridgeError('attachment-integrity', 'Attachment exceeded its recorded size.')
      chunks.push(Buffer.from(chunk))
    }
    bytes = Buffer.concat(chunks, length)
  }
  const sha256 = digestId.exec(attachmentId)[1]
  if (bytes.length !== attachment.bytes || createHash('sha256').update(bytes).digest('hex') !== sha256) {
    throw bridgeError('attachment-integrity', 'Attachment does not match the original digest.')
  }
  const end = request.op === 'attachment-data' ? bytes.length : Math.min(bytes.length, offset + chunkSize)
  return { offset, total: bytes.length, sha256, mediaType: attachment.mediaType,
    name: attachment.name, kind, data: bytes.subarray(offset, end).toString('base64'),
    ...(end < bytes.length ? { nextOffset: end } : {}) }
}

export async function importAttachment(ctx, path, sessionId, signal) {
  if (typeof path !== 'string' || !isAbsolute(path)) throw bridgeError('invalid-attachment', 'Choose an absolute file path.')
  const file = await open(path, 'r')
  let data
  try {
    const original = await file.stat()
    if (!original.isFile() || original.size > attachmentLimit) {
      throw bridgeError('invalid-attachment', 'Choose a regular file up to 16 MiB.')
    }
    data = Buffer.alloc(original.size)
    let bytesRead = 0
    while (bytesRead < data.length) {
      const chunk = await file.read({ buffer: data, offset: bytesRead, length: data.length - bytesRead, position: bytesRead })
      if (!chunk.bytesRead) break
      bytesRead += chunk.bytesRead
    }
    const after = await file.stat()
    if (bytesRead !== data.length || after.size !== original.size || after.mtimeMs !== original.mtimeMs) {
      throw bridgeError('attachment-changed', 'The file changed while it was being read.')
    }
  } finally {
    await file.close()
  }
  const name = basename(path)
  const mediaType = imageTypes.get(extname(name).toLowerCase())
  if (mediaType) return { type: 'image', data: data.toString('base64'), name, mediaType }
  const uploads = ctx.get('fileUploads')
  if (!uploads?.uploadStream) throw bridgeError('attachment-unavailable', 'The DSH file upload service is unavailable.')
  async function* chunks() { yield data }
  const { receiptId } = await uploads.uploadStream({ sessionId, data: chunks(), name, signal })
  return { type: 'file', receiptId }
}

export async function codexAttachment(ctx, session, attachmentId, sourceSeq, invoke) {
  if (!digestId.test(attachmentId)) throw bridgeError('invalid-attachment', 'Choose the exact original attachment digest.')
  if (sourceSeq === undefined) {
    const recent = session.snapshotEvents(Math.max(0, session.seq - 500))
    sourceSeq = recent.findLast(event => attachmentSources(event)
      .some(item => item.attachment.attachmentId === attachmentId))?.seq
  }
  if (sourceSeq === undefined) throw bridgeError('attachment-not-in-session', 'Choose the source message for this attachment.')
  const result = await readAttachments(ctx, session.id, { op: 'attachment-data', seq: sourceSeq, attachmentId }, invoke)
  if (result.kind === 'image') {
    if (!/^image\/(?:png|jpeg|webp|gif)$/.test(result.mediaType)) {
      throw bridgeError('invalid-attachment', 'Unsupported image type for Codex.')
    }
    return result
  }
  const path = ctx.get('attachments')?.fileHostPath({ attachmentId, name: result.name, bytes: result.total })
  if (typeof path !== 'string' || !isAbsolute(path)) throw bridgeError('attachment-unavailable', 'Cannot locate the verified local file.')
  return { kind: 'file', path, name: result.name, sha256: result.sha256 }
}
