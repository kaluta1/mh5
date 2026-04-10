import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Strip HTML tags and common entities for safe plain-text display (no raw tags for users). */
export function htmlToPlainText(html: string): string {
  if (!html) return ''
  let s = html.replace(/<[^>]*>/g, ' ')
  s = s.replace(/&nbsp;/gi, ' ')
  s = s.replace(/&amp;/gi, '&')
  s = s.replace(/&quot;/gi, '"')
  s = s.replace(/&#39;/g, "'")
  s = s.replace(/&lt;/gi, '<')
  s = s.replace(/&gt;/gi, '>')
  s = s.replace(/\s+/g, ' ').trim()
  return s
}
