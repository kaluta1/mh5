/**
 * Use with translation keys: if `t` returns empty (missing i18n), show readable fallback — never a raw key.
 */
export function trOr(
  t: (key: string) => string,
  i18nKey: string,
  fallback: string
): string {
  const v = t(i18nKey)
  if (v && v.trim() !== "" && v !== i18nKey) {
    return v
  }
  return fallback
}
