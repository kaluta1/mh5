import { NextRequest, NextResponse } from 'next/server'
import { API_URL } from '@/lib/config'

const VALID_TASKS = ['payments', 'contest-status', 'season-migration', 'monthly-round']

export async function POST(
  request: NextRequest,
  { params }: { params: { task: string } }
) {
  const { task } = params

  if (!VALID_TASKS.includes(task)) {
    return NextResponse.json({ error: 'Invalid scheduler task' }, { status: 404 })
  }

  // Vercel Cron sends Authorization: Bearer <CRON_SECRET>.
  // We forward that value as x-cron-secret to the backend.
  const authHeader = request.headers.get('authorization') || ''
  const cronSecret = authHeader.startsWith('Bearer ')
    ? authHeader.slice('Bearer '.length)
    : request.headers.get('x-cron-secret') || ''

  if (!cronSecret) {
    return NextResponse.json({ error: 'Missing cron secret' }, { status: 401 })
  }

  const backendUrl = `${API_URL}/api/v1/scheduler/run/${task}`

  try {
    const res = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-cron-secret': cronSecret,
      },
      cache: 'no-store',
    })

    const bodyText = await res.text()
    let body: unknown
    try {
      body = JSON.parse(bodyText)
    } catch {
      body = bodyText
    }

    return NextResponse.json(body, { status: res.status })
  } catch (err) {
    return NextResponse.json(
      { error: 'Failed to proxy cron request', detail: String(err) },
      { status: 502 }
    )
  }
}
