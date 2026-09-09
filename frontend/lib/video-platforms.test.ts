import { describe, expect, it } from 'vitest'
import { convertToEmbedUrl, detectVideoPlatform, isValidVideoUrl } from './utils/video-platforms'

describe('safe video provider resolution', () => {
  it.each([
    ['https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'youtube'],
    ['https://youtu.be/dQw4w9WgXcQ', 'youtube'],
    ['https://vimeo.com/123456', 'vimeo'],
    ['https://www.tiktok.com/@user/video/123456789', 'tiktok'],
    ['https://www.facebook.com/watch/?v=123456', 'facebook'],
    ['https://cdn.example/video.mp4', 'direct'],
  ])('recognizes %s as %s', (url, platform) => {
    expect(detectVideoPlatform(url)).toBe(platform)
  })

  it.each([
    'https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ',
    'https://evil-youtube.com/watch?v=dQw4w9WgXcQ',
    'javascript:alert(1)',
    'https://cdn.example/file.html',
  ])('rejects spoofed or unsupported URL %s', url => {
    expect(detectVideoPlatform(url)).toBe('unknown')
    expect(isValidVideoUrl(url)).toBe(false)
  })

  it('fails closed when an allowed provider URL lacks a valid video ID', () => {
    expect(convertToEmbedUrl('https://youtube.com/watch?v=short').platform).toBe('unknown')
    expect(convertToEmbedUrl('https://vimeo.com/not-a-number').platform).toBe('unknown')
  })

  it('creates fixed-provider embed URLs only', () => {
    expect(convertToEmbedUrl('https://youtu.be/dQw4w9WgXcQ').embedUrl)
      .toBe('https://www.youtube.com/embed/dQw4w9WgXcQ')
    expect(convertToEmbedUrl('https://vimeo.com/123456').embedUrl)
      .toBe('https://player.vimeo.com/video/123456')
  })
})
