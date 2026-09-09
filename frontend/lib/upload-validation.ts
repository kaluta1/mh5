const MAX_UPLOAD_BYTES = 32 * 1024 * 1024

type Rule = {
  extensions: string[]
  mimeTypes: string[]
  matches: (bytes: Uint8Array) => boolean
}

const rules: Rule[] = [
  { extensions: ['.jpg', '.jpeg'], mimeTypes: ['image/jpeg'], matches: b => b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff },
  { extensions: ['.png'], mimeTypes: ['image/png'], matches: b => b.length >= 8 && [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a].every((v, i) => b[i] === v) },
  { extensions: ['.gif'], mimeTypes: ['image/gif'], matches: b => String.fromCharCode(...b.slice(0, 6)) === 'GIF87a' || String.fromCharCode(...b.slice(0, 6)) === 'GIF89a' },
  { extensions: ['.webp'], mimeTypes: ['image/webp'], matches: b => String.fromCharCode(...b.slice(0, 4)) === 'RIFF' && String.fromCharCode(...b.slice(8, 12)) === 'WEBP' },
  { extensions: ['.mp4'], mimeTypes: ['video/mp4'], matches: b => String.fromCharCode(...b.slice(4, 8)) === 'ftyp' },
  { extensions: ['.webm'], mimeTypes: ['video/webm'], matches: b => b[0] === 0x1a && b[1] === 0x45 && b[2] === 0xdf && b[3] === 0xa3 },
  { extensions: ['.mp3'], mimeTypes: ['audio/mpeg'], matches: b => String.fromCharCode(...b.slice(0, 3)) === 'ID3' || (b[0] === 0xff && (b[1] & 0xe0) === 0xe0) },
  { extensions: ['.wav'], mimeTypes: ['audio/wav', 'audio/x-wav'], matches: b => String.fromCharCode(...b.slice(0, 4)) === 'RIFF' && String.fromCharCode(...b.slice(8, 12)) === 'WAVE' },
  { extensions: ['.pdf'], mimeTypes: ['application/pdf'], matches: b => String.fromCharCode(...b.slice(0, 5)) === '%PDF-' },
]

export function validateUploadMetadata(file: Pick<File, 'name' | 'size' | 'type'>): string | null {
  if (!file.name || file.name.includes('/') || file.name.includes('\\') || file.name.includes('\0')) return 'Invalid filename'
  if (file.size <= 0) return 'File is empty'
  if (file.size > MAX_UPLOAD_BYTES) return 'File exceeds the 32 MB limit'
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!rules.some(rule => rule.extensions.includes(extension) && rule.mimeTypes.includes(file.type.toLowerCase()))) {
    return 'Unsupported file extension or MIME type'
  }
  return null
}

export function validateUploadSignature(file: Pick<File, 'name' | 'type'>, bytes: Uint8Array): string | null {
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  const rule = rules.find(item => item.extensions.includes(extension) && item.mimeTypes.includes(file.type.toLowerCase()))
  if (!rule || !rule.matches(bytes)) return 'File content does not match its extension and MIME type'
  return null
}
