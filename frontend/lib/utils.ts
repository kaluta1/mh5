import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

import { descriptionToPlainText } from "./description-text"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Strip HTML tags and entities for safe plain-text display (no raw tags for users). */
export function htmlToPlainText(html: string): string {
  return descriptionToPlainText(html)
}
