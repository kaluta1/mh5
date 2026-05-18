import type { Metadata } from 'next'
import { headers } from 'next/headers'
import { redirect } from 'next/navigation'
import {
  SITE_ORIGIN,
  fetchContestantSharePreview,
  isSocialCrawler,
} from '@/lib/share-preview-server'

export const dynamic = 'force-dynamic'

type PageProps = {
  params: Promise<{ id: string }>
  searchParams: Promise<{ ref?: string }>
}

export async function generateMetadata({ params, searchParams }: PageProps): Promise<Metadata> {
  const { id } = await params
  const { ref } = await searchParams
  const preview = await fetchContestantSharePreview(id)
  const shareUrl = ref
    ? `${SITE_ORIGIN}/s/c/${id}?ref=${encodeURIComponent(ref)}`
    : `${SITE_ORIGIN}/s/c/${id}`

  return {
    metadataBase: new URL(SITE_ORIGIN),
    title: preview.title,
    description: preview.description,
    openGraph: {
      type: 'article',
      url: shareUrl,
      siteName: 'MyHigh5',
      title: preview.title,
      description: preview.description,
      images: [
        {
          url: preview.imageUrl,
          width: 1200,
          height: 630,
          alt: preview.title,
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title: preview.title,
      description: preview.description,
      images: [preview.imageUrl],
    },
    alternates: {
      canonical: shareUrl,
    },
  }
}

export default async function ShareContestantPage({ params, searchParams }: PageProps) {
  const { id } = await params
  const { ref } = await searchParams
  const preview = await fetchContestantSharePreview(id)
  const destination = ref
    ? `/contestants/${id}?ref=${encodeURIComponent(ref)}`
    : `/contestants/${id}`

  const userAgent = (await headers()).get('user-agent')
  if (!isSocialCrawler(userAgent)) {
    redirect(destination)
  }

  return (
    <main
      style={{
        fontFamily: 'system-ui, sans-serif',
        maxWidth: 640,
        margin: '40px auto',
        padding: '0 16px',
      }}
    >
      <h1 style={{ fontSize: 24, marginBottom: 12 }}>{preview.title}</h1>
      <p style={{ color: '#444', lineHeight: 1.5 }}>{preview.description}</p>
      <p style={{ marginTop: 24 }}>
        <a href={destination} style={{ color: '#1e40af', fontWeight: 600 }}>
          Open on MyHigh5
        </a>
      </p>
    </main>
  )
}
