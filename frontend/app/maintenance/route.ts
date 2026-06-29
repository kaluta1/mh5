import { NextResponse } from 'next/server'

/** Maintenance mode removed — send visitors to the live site. */
export function GET() {
  return NextResponse.redirect(new URL('/', process.env.NEXT_PUBLIC_APP_URL || 'https://myhigh5.com'))
}
