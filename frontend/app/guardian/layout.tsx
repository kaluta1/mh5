import type { Metadata } from 'next'

// Guardian consent pages are private, token-based pages: never indexed.
export const metadata: Metadata = {
  title: 'Parent or guardian approval | MyHigh5',
  robots: { index: false, follow: false },
}

export default function GuardianLayout({ children }: { children: React.ReactNode }) {
  return children
}
