import { describe, expect, it } from 'vitest'

import {
  descriptionPreview,
  descriptionToDisplayText,
  descriptionToParagraphs,
  descriptionToPlainText,
} from './description-text'
import { htmlToPlainText } from './utils'

// The stored description of the production entry that showed raw tags.
const STORED = '<p><strong>UTAPENDA! UMAFIA WA KONTAWA AKICHANA FREESTYLE HII BEAT LA KINANDA</strong></p><p><br></p><p><br></p>'

const NO_MARKUP = /<\/?[a-z!][^>]*>/i

describe('list preview is plain text', () => {
  it('shows the words of a rich-text description, with no literal HTML', () => {
    const text = descriptionToPlainText(STORED)
    expect(text).toBe('UTAPENDA! UMAFIA WA KONTAWA AKICHANA FREESTYLE HII BEAT LA KINANDA')
    expect(text).not.toMatch(NO_MARKUP)
    expect(text).not.toContain('<')
  })

  it('separates paragraphs with a space instead of gluing words together', () => {
    expect(descriptionToPlainText('<p>First</p><p>Second</p><ul><li>a</li><li>b</li></ul>')).toBe('First Second a b')
  })

  it('decodes entities, including numeric ones', () => {
    expect(descriptionToPlainText('Tom &amp; Jerry&nbsp;&#39;live&#x27; &quot;now&quot;')).toBe(`Tom & Jerry 'live' "now"`)
  })

  it('leaves no tag when the markup was stored escaped (single or double)', () => {
    for (const stored of [
      '&lt;p&gt;Hello&lt;/p&gt;',
      '&amp;lt;script&amp;gt;alert(1)&amp;lt;/script&amp;gt;Hello',
      '&lt;img src=x onerror=alert(1)&gt;Hello',
    ]) {
      const text = descriptionToPlainText(stored)
      expect(text).not.toMatch(NO_MARKUP)
      expect(text).toContain('Hello')
    }
  })

  it('drops script, style and embedded-frame content entirely', () => {
    const text = descriptionToPlainText(
      '<p>Safe</p><script>alert("x")</script><style>p{color:red}</style><iframe src="https://evil.example"></iframe><!-- hidden -->',
    )
    expect(text).toBe('Safe')
  })

  it('drops event handlers, javascript: links and unterminated tags', () => {
    const text = descriptionToPlainText('<a href="javascript:alert(1)" onclick="steal()">Click</a> <img src=x onerror=alert(1)')
    expect(text).toBe('Click')
    expect(text).not.toMatch(/onclick|onerror|javascript:/i)
  })

  it('keeps ordinary text that merely contains angle brackets', () => {
    expect(descriptionToPlainText('I <3 this, 2 < 3 and 5 > 4')).toBe('I <3 this, 2 < 3 and 5 > 4')
  })

  it('handles empty input', () => {
    for (const value of [undefined, null, '', '<p><br></p>']) {
      expect(descriptionToPlainText(value)).toBe('')
    }
  })

  it('truncates previews on the plain text, never in the middle of a tag', () => {
    const preview = descriptionPreview(STORED, 20)
    expect(preview).toBe('UTAPENDA! UMAFIA WA...')
    expect(preview).not.toContain('<')
  })

  it('is what the shared htmlToPlainText helper returns', () => {
    expect(htmlToPlainText(STORED)).toBe(descriptionToPlainText(STORED))
    expect(htmlToPlainText('&lt;b&gt;x&lt;/b&gt;')).toBe('x')
  })
})

describe('detail text is sanitized to plain paragraphs', () => {
  it('keeps paragraph and line breaks as the only formatting', () => {
    expect(descriptionToParagraphs('<p><strong>Title</strong></p><p>Line one<br>Line two</p><p><br></p>')).toEqual([
      'Title',
      'Line one',
      'Line two',
    ])
    expect(descriptionToDisplayText('<p>One</p><p>Two</p>')).toBe('One\nTwo')
  })

  it('never returns markup, whatever was stored', () => {
    const hostile = [
      '<p onclick="x()">Hi</p><script>alert(1)</script>',
      '<svg/onload=alert(1)>Hi',
      '<p>Hi</p><img src="x" onerror="alert(1)">',
      '&lt;script&gt;alert(1)&lt;/script&gt;Hi',
      '<a href="javascript:alert(1)">Hi</a>',
    ]
    for (const stored of hostile) {
      const paragraphs = descriptionToParagraphs(stored)
      expect(paragraphs.join(' ')).toContain('Hi')
      for (const paragraph of paragraphs) {
        expect(paragraph).not.toMatch(NO_MARKUP)
        expect(paragraph).not.toMatch(/onclick|onerror|onload|javascript:/i)
      }
    }
  })
})
