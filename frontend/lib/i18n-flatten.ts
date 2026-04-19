/** Flatten nested JSON leaves into dot-notation keys (only string values). */
export function flattenStringLeaves(
  obj: unknown,
  prefix = "",
): Record<string, string> {
  const out: Record<string, string> = {}
  if (obj === null || obj === undefined) return out
  if (typeof obj === "string") {
    if (prefix) out[prefix] = obj
    return out
  }
  if (typeof obj !== "object" || Array.isArray(obj)) return out

  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    const p = prefix ? `${prefix}.${k}` : k
    if (typeof v === "string") {
      out[p] = v
    } else if (v && typeof v === "object" && !Array.isArray(v)) {
      Object.assign(out, flattenStringLeaves(v, p))
    }
  }
  return out
}
