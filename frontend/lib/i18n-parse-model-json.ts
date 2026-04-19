/**
 * Models sometimes wrap keys in `{ "translations": { ... } }` instead of a flat map.
 */
export function extractStringMapFromModelJson(
  parsed: Record<string, unknown>,
  expectedKeys: string[],
): Record<string, string> {
  let root: Record<string, unknown> = parsed

  const hasAnyExpectedKey = expectedKeys.some((k) => k in root)
  const wrapped =
    !hasAnyExpectedKey &&
    root.translations &&
    typeof root.translations === "object" &&
    root.translations !== null &&
    !Array.isArray(root.translations)

  if (wrapped) {
    root = root.translations as Record<string, unknown>
  }

  const out: Record<string, string> = {}
  for (const k of expectedKeys) {
    const v = root[k]
    if (typeof v === "string" && v.length > 0) {
      out[k] = v
    }
  }
  return out
}
