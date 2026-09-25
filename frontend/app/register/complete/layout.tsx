import type { Metadata } from 'next'

// Token-based completion page: never indexed.
export const metadata: Metadata = {
  title: 'Finish creating your account | MyHigh5',
  robots: { index: false, follow: false },
}

export default function CompleteRegistrationLayout({ children }: { children: React.ReactNode }) {
  return children
}
