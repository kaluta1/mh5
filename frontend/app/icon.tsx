import { ImageResponse } from 'next/og'

export const size = { width: 32, height: 32 }
export const contentType = 'image/png'

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #2563eb 0%, #0891b2 100%)',
          color: 'white',
          fontSize: 18,
          fontWeight: 800,
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        5
      </div>
    ),
    { ...size },
  )
}
