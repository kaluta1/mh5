import { NextResponse } from "next/server"
import { extractStringMapFromModelJson } from "@/lib/i18n-parse-model-json"

export const runtime = "nodejs"
export const maxDuration = 60

/**
 * OpenAI-compatible Chat Completions (default: `https://api.openai.com/v1`).
 * Set one of: `OPENAI_API_KEY`, `AI_API_KEY`, or `CURSOR_API_KEY` in `.env.local`.
 * Note: "Cursor API" in the IDE sense is separate; production apps typically use OpenAI, Anthropic, or DeepL keys.
 */
function resolveApiKey() {
  return process.env.OPENAI_API_KEY || process.env.AI_API_KEY || process.env.CURSOR_API_KEY
}

function resolveBaseUrl() {
  const b = process.env.AI_API_BASE_URL || "https://api.openai.com/v1"
  return b.replace(/\/$/, "")
}

function resolveModel() {
  return process.env.AI_TRANSLATION_MODEL || "gpt-4o-mini"
}

export async function POST(req: Request) {
  const key = resolveApiKey()
  if (!key) {
    return NextResponse.json(
      {
        error:
          "AI translation is not configured. Add OPENAI_API_KEY (or AI_API_KEY / CURSOR_API_KEY for OpenAI-compatible keys) to .env.local.",
      },
      { status: 503 },
    )
  }

  let body: { targetLocale?: string; entries?: Record<string, string> }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }

  const targetLocale = body.targetLocale
  const entries = body.entries
  if (!targetLocale || typeof targetLocale !== "string") {
    return NextResponse.json({ error: "targetLocale required" }, { status: 400 })
  }
  if (!entries || typeof entries !== "object" || Array.isArray(entries)) {
    return NextResponse.json({ error: "entries object required" }, { status: 400 })
  }

  const keys = Object.keys(entries)
  if (keys.length === 0) {
    return NextResponse.json({ translations: {} })
  }
  if (keys.length > 200) {
    return NextResponse.json({ error: "Max 200 keys per request" }, { status: 400 })
  }

  let localeName: string
  try {
    localeName =
      new Intl.DisplayNames(["en"], { type: "language" }).of(
        targetLocale.replace(/_/g, "-"),
      ) || targetLocale
  } catch {
    localeName = targetLocale
  }

  const userPayload = JSON.stringify(entries)
  const prompt = `Translate UI strings into ${localeName} (language code: ${targetLocale}).

Return ONLY valid JSON: one object mapping each input key to the translated string.

Rules:
- Preserve placeholders exactly: {count}, {name}, %s, \\n, and similar must remain usable.
- Do not rename keys. Include every key from the input.
- Keep the brand name "MyHigh5" in Latin letters unless the script requires transliteration for readability.
- Short, natural mobile / dashboard phrasing.

Input JSON (key = dotted path, value = English):
${userPayload}`

  const res = await fetch(`${resolveBaseUrl()}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: resolveModel(),
      temperature: 0.2,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content:
            "You are a professional product UI translator. Respond with JSON only.",
        },
        { role: "user", content: prompt },
      ],
    }),
  })

  if (!res.ok) {
    const t = await res.text()
    console.error("[api/i18n/translate]", res.status, t.slice(0, 500))
    return NextResponse.json(
      { error: "Translation provider error", detail: t.slice(0, 300) },
      { status: 502 },
    )
  }

  const data = (await res.json()) as {
    choices?: Array<{ message?: { content?: string } }>
  }
  const text = data.choices?.[0]?.message?.content
  if (!text) {
    return NextResponse.json({ error: "Empty model response" }, { status: 502 })
  }

  let parsed: Record<string, unknown>
  try {
    parsed = JSON.parse(text) as Record<string, unknown>
  } catch {
    return NextResponse.json({ error: "Model returned non-JSON" }, { status: 502 })
  }

  const extracted = extractStringMapFromModelJson(parsed, keys)
  const out: Record<string, string> = {}
  for (const k of keys) {
    const v = extracted[k]
    if (typeof v === "string" && v.length > 0) {
      out[k] = v
    } else {
      out[k] = entries[k]
    }
  }

  return NextResponse.json({ translations: out })
}
