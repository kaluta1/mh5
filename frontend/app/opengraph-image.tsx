import { ImageResponse } from 'next/og'

export const runtime = 'edge'
export const alt = 'MyHigh5'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #1e40af 0%, #0891b2 100%)',
          color: 'white',
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        <div style={{ fontSize: 72, fontWeight: 800, letterSpacing: -2 }}>MyHigh5</div>
        <div style={{ fontSize: 32, marginTop: 16, opacity: 0.9 }}>Vote. Share. Win.</div>
      </div>
    ),
    { ...size }
  )
}
