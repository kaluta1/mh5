import { lookup } from 'node:dns/promises'
import { isIP } from 'node:net'

function isPrivateAddress(address: string): boolean {
  const normalized = address.toLowerCase().replace(/^::ffff:/, '')
  if (
    normalized === '::1' || normalized === '::' || normalized.startsWith('fe80:') ||
    normalized.startsWith('fc') || normalized.startsWith('fd')
  ) return true
  const parts = normalized.split('.').map(Number)
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) return false
  return (
    parts[0] === 0 || parts[0] === 10 || parts[0] === 127 ||
    (parts[0] === 169 && parts[1] === 254) ||
    (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
    (parts[0] === 192 && parts[1] === 168) ||
    (parts[0] === 100 && parts[1] >= 64 && parts[1] <= 127) ||
    parts[0] >= 224
  )
}

export async function assertSafeRemoteUrl(target: URL): Promise<void> {
  if (!['http:', 'https:'].includes(target.protocol) || target.username || target.password) {
    throw new Error('URL not allowed')
  }
  const hostname = target.hostname.toLowerCase().replace(/^\[|\]$/g, '')
  if (
    hostname === 'localhost' || hostname.endsWith('.localhost') ||
    hostname.endsWith('.local') || hostname.endsWith('.internal')
  ) throw new Error('URL not allowed')

  if (isIP(hostname)) {
    if (isPrivateAddress(hostname)) throw new Error('URL not allowed')
    return
  }
  const addresses = await lookup(hostname, { all: true, verbatim: true })
  if (!addresses.length || addresses.some(({ address }) => isPrivateAddress(address))) {
    throw new Error('URL not allowed')
  }
}
