import { Metadata } from "next"
import { createMetadata } from "../../metadata"
import { getMetadataTranslations, detectLanguageFromHeaders } from "@/lib/metadata-translations"
import { headers } from "next/headers"

const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://myhigh5.com"
const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function generateMetadata({
  params,
}: {
  params: { id: string }
}): Promise<Metadata> {
  // Détecter la langue
  const headersList = headers()
  const lang = detectLanguageFromHeaders(headersList)
  const translations = getMetadataTranslations(lang)
  // Traductions en anglais pour les partages sociaux
  const englishTranslations = getMetadataTranslations('en')

  try {
    // Appel direct à l'API backend pour récupérer les données du contestant
    const response = await fetch(`${apiUrl}/api/v1/contestants/${params.id}`, {
      next: { revalidate: 3600 }, // Cache pendant 1 heure
    })
    
    if (!response.ok) {
      throw new Error("Contestant not found")
    }
    
    const contestant = await response.json()
    
    if (!contestant) {
      return createMetadata({
        title: `${englishTranslations.pages.contests.title.split(' - ')[0]} - ${englishTranslations.siteName}`, // Titre en anglais
        description: `Discover this participant on ${englishTranslations.siteName}`, // Description en anglais
        url: `/contestants/${params.id}`,
        language: lang,
      })
    }

    // Utiliser le nom du participant mais avec une description en anglais
    const title = contestant.title || `${contestant.author_name || 'Participant'} - ${englishTranslations.siteName}`
    const description = contestant.description 
      ? contestant.description 
      : `Discover ${contestant.author_name || 'this participant'} on ${englishTranslations.siteName}. Vote and support!`

    // Image de partage : toujours l'image du concours (pas l'avatar de l'auteur)
    let image = `${appUrl}/thumbnails.png`
    try {
      const contestId = contestant.contest_id || contestant.contestId
      if (contestId) {
        const contestResp = await fetch(`${apiUrl}/api/v1/contests/${contestId}`, {
          next: { revalidate: 3600 },
        })
        if (contestResp.ok) {
          const contestData = await contestResp.json()
          image = contestData.cover_image_url || contestData.image_url || image
        }
      }
    } catch (err) {
      console.error("Error loading contest for metadata:", err)
    }
    // S'assurer que l'image est une URL absolue
    if (!image.startsWith('http')) {
      image = image.startsWith('/') ? `${appUrl}${image}` : `${appUrl}/${image}`
    }

    return createMetadata({
      title, // Titre avec nom du participant
      description, // Description en anglais
      image,
      url: `/contestants/${params.id}`,
      type: "profile",
      language: lang,
    })
  } catch (error) {
    console.error("Error generating metadata for contestant:", error)
    return createMetadata({
      title: `${englishTranslations.pages.contests.title.split(' - ')[0]} - ${englishTranslations.siteName}`, // Titre en anglais
      description: `Discover this participant on ${englishTranslations.siteName}`, // Description en anglais
      url: `/contestants/${params.id}`,
      language: lang,
    })
  }
}

export default function ContestantLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}
