/**
 * Entry descriptions are written in a rich-text editor and stored as HTML.
 * Stored HTML is never rendered as markup anywhere: these helpers turn it into
 * plain text, which React then escapes like any other string.
 *
 *  - descriptionToPlainText: one line, for cards, tables and list previews.
 *  - descriptionToParagraphs: the same text with paragraph breaks kept, for
 *    detail views.
 */

const NAMED_ENTITIES: Record<string, string> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: ' ',
}

/** Tags whose end (or self) marks a line break in the visible text. */
const BLOCK_BREAK = /<\s*br\s*\/?\s*>|<\s*\/\s*(p|div|li|ul|ol|h[1-6]|blockquote|pre|tr)\s*>/gi
/** Elements whose content is never visible text. */
const INVISIBLE_ELEMENT = /<\s*(script|style|iframe|object|embed|noscript|template)\b[\s\S]*?<\s*\/\s*\1\s*>/gi
const ANY_TAG = /<\/?[a-zA-Z!][^>]*>/g
const COMMENT = /<!--[\s\S]*?-->/g
/** An opening tag that was never closed (e.g. a truncated `<img src=x onerror=`). */
const DANGLING_TAG = /<\/?[a-zA-Z][^<>]*$/g

function decodeEntities(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);/gi, (match, body: string) => {
    const key = body.toLowerCase()
    if (key.startsWith('#')) {
      const code = key[1] === 'x' ? parseInt(key.slice(2), 16) : parseInt(key.slice(1), 10)
      if (!Number.isFinite(code) || code <= 0 || code > 0x10ffff) return ''
      try {
        return String.fromCodePoint(code)
      } catch {
        return ''
      }
    }
    return key in NAMED_ENTITIES ? NAMED_ENTITIES[key] : match
  })
}

function stripMarkup(text: string): string {
  return text.replace(COMMENT, ' ').replace(INVISIBLE_ELEMENT, ' ').replace(ANY_TAG, ' ').replace(DANGLING_TAG, ' ')
}

/** Visible text of a stored description, with "\n" at paragraph boundaries. */
function visibleText(html: string | null | undefined): string {
  if (!html) return ''
  let text = String(html).replace(COMMENT, ' ').replace(INVISIBLE_ELEMENT, ' ').replace(BLOCK_BREAK, '\n')
  text = stripMarkup(text)
  // Escaped markup (`&lt;script&gt;`) becomes markup-looking text once decoded:
  // decode and strip until nothing changes (bounded), so no tag survives.
  for (let i = 0; i < 5; i += 1) {
    const next = stripMarkup(decodeEntities(text).replace(BLOCK_BREAK, '\n'))
    if (next === text) break
    text = next
  }
  return text.replace(/ /g, ' ')
}

/** One-line plain text for cards, tables and list previews. */
export function descriptionToPlainText(html: string | null | undefined): string {
  return visibleText(html).replace(/\s+/g, ' ').trim()
}

/** Plain-text paragraphs for detail views (formatting reduced to paragraph breaks). */
export function descriptionToParagraphs(html: string | null | undefined): string[] {
  return visibleText(html)
    .split('\n')
    .map((line) => line.replace(/[ \t\r\f\v]+/g, ' ').trim())
    .filter((line) => line.length > 0)
}

/** Detail text as a single string; render inside `whitespace-pre-line`. */
export function descriptionToDisplayText(html: string | null | undefined): string {
  return descriptionToParagraphs(html).join('\n')
}

/** Truncated one-line preview. */
export function descriptionPreview(html: string | null | undefined, maxLength = 160): string {
  const text = descriptionToPlainText(html)
  return text.length > maxLength ? `${text.slice(0, maxLength).trimEnd()}...` : text
}
