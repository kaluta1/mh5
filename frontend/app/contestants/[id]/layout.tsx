import { Metadata } from 'next'

async function getContestantData(contestantId: string): Promise<any> {
  try {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const response = await fetch(`${apiUrl}/api/v1/contestants/${contestantId}`, {
      cache: 'no-store'
    })
    if (!response.ok) {
      return null
    }
    return await response.json()
  } catch (error) {
    console.error('Error fetching contestant for metadata:', error)
    return null
  }
}

export async function generateMetadata({ params }: { params: { id: string } }): Promise<Metadata> {
  const contestant = await getContestantData(params.id)
  
  if (!contestant) {
    return {
      title: 'Contestant - MyFav',
      description: 'Découvrez ce participant sur MyFav'
    }
  }

  const baseUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'
  const title = contestant.title || `${contestant.author_name || 'Contestant'} - MyFav`
  const description = contestant.description || `Découvrez ${contestant.author_name || 'ce participant'} sur MyFav`
  
  // Récupérer la première image ou vidéo pour le preview
  let imageUrl = contestant.author_avatar_url
  if (contestant.image_media_ids) {
    try {
      const imageIds = JSON.parse(contestant.image_media_ids)
      if (imageIds && imageIds.length > 0) {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
        imageUrl = `${apiUrl}/api/v1/media/${imageIds[0]}`
      }
    } catch (e) {
      // Si ce n'est pas un JSON, utiliser directement
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      imageUrl = `${apiUrl}/api/v1/media/${contestant.image_media_ids}`
    }
  } else if (contestant.video_media_ids) {
    try {
      const videoIds = JSON.parse(contestant.video_media_ids)
      if (videoIds && videoIds.length > 0) {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
        imageUrl = `${apiUrl}/api/v1/media/${videoIds[0]}/thumbnail`
      }
    } catch (e) {
      // Si ce n'est pas un JSON, utiliser directement
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      imageUrl = `${apiUrl}/api/v1/media/${contestant.video_media_ids}/thumbnail`
    }
  }

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: 'profile',
      url: `${baseUrl}/contestants/${params.id}`,
      images: imageUrl ? [{ url: imageUrl }] : [],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: imageUrl ? [imageUrl] : [],
    },
  }
}

export default function ContestantLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}

