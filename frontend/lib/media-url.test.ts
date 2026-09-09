import { describe, expect, it } from 'vitest'
import { normalizeMediaUrl, toStoredMediaUrl, withMediaCacheBust } from './media-url'

describe('media URL compatibility and safety', () => {
  it('stores canonical API paths without an environment host', () => {
    expect(toStoredMediaUrl('https://old.example/api/v1/media/file/42/photo.png?x=1'))
      .toBe('/api/v1/media/file/42/photo.png')
  })

  it('converts legacy media and S3 upload paths', () => {
    expect(toStoredMediaUrl('/media/7/avatar.jpg')).toBe('/api/v1/media/file/7/avatar.jpg')
    expect(toStoredMediaUrl('https://bucket.test/uploads/8/image.webp')).toBe('/api/v1/media/file/8/image.webp')
  })

  it('preserves HTTPS external media', () => {
    expect(normalizeMediaUrl('https://cdn.example/photo.jpg')).toBe('https://cdn.example/photo.jpg')
  })

  it('upgrades legacy external HTTP media to HTTPS', () => {
    expect(normalizeMediaUrl('http://cdn.example/photo.jpg')).toBe('https://cdn.example/photo.jpg')
  })

  it('rebinds localhost historical media to the configured public origin', () => {
    const result = normalizeMediaUrl('http://127.0.0.1:8000/storage/avatars/demo.png')
    expect(result).toMatch(/\/storage\/avatars\/demo\.png$/)
    expect(result).not.toContain('127.0.0.1')
  })

  it.each(['javascript:alert(1)', 'file:///etc/passwd', 'C:\\secret.png', '//evil.test/image.png'])('rejects unsafe reference %s', value => {
    expect(normalizeMediaUrl(value)).toBe('')
  })

  it('allows safe raster data previews but rejects SVG data', () => {
    expect(normalizeMediaUrl('data:image/png;base64,AA==')).toBe('data:image/png;base64,AA==')
    expect(normalizeMediaUrl('data:image/svg+xml,<svg/>')).toBe('')
  })

  it('rejects encoded traversal in canonical media filenames', () => {
    expect(normalizeMediaUrl('/api/v1/media/file/1/%2Fsecret.png')).toBe('')
  })

  it('adds cache busting without changing data URLs', () => {
    expect(withMediaCacheBust('https://cdn.example/a.png', 5)).toContain('?v=5')
    expect(withMediaCacheBust('data:image/png;base64,AA==', 5)).toBe('data:image/png;base64,AA==')
  })
})
