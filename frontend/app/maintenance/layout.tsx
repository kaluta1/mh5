import type { Metadata } from 'next'

const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://myhigh5.com'

export const metadata: Metadata = {
  title: 'Maintenance | MyHigh5',
  description: 'MyHigh5 is temporarily unavailable while maintenance is in progress.',
  robots: {
    index: false,
    follow: false,
    googleBot: {
      index: false,
      follow: false,
      'max-snippet': 0,
      'max-image-preview': 'none',
      'max-video-preview': 0,
    },
  },
  alternates: {
    canonical: `${appUrl}/maintenance`,
  },
}

export default function MaintenanceLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
