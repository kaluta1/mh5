import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Clear cache',
  robots: { index: false, follow: false },
}

export default function ClearCacheLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
