import { describe, expect, it } from 'vitest'
import { validateUploadMetadata, validateUploadSignature } from './upload-validation'

const file = (name: string, type: string, size = 10) => ({ name, type, size } as File)

describe('server upload validation helpers', () => {
  it('accepts consistent PNG metadata and signature', () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
    expect(validateUploadMetadata(file('photo.png', 'image/png'))).toBeNull()
    expect(validateUploadSignature(file('photo.png', 'image/png'), png)).toBeNull()
  })

  it.each([
    ['../photo.png', 'image/png', 10],
    ['photo.svg', 'image/svg+xml', 10],
    ['photo.png', 'image/jpeg', 10],
    ['photo.png', 'image/png', 33 * 1024 * 1024],
  ])('rejects unsafe metadata for %s', (name, type, size) => {
    expect(validateUploadMetadata(file(name as string, type as string, size as number))).not.toBeNull()
  })

  it('rejects content that does not match metadata', () => {
    expect(validateUploadSignature(file('photo.png', 'image/png'), new Uint8Array([1, 2, 3]))).not.toBeNull()
  })
})
