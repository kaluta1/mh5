import { Metadata } from "next"
import { createMetadata } from "../../../metadata"
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
    // Appel direct à l'API backend pour récupérer les données du concours
    const response = await fetch(`${apiUrl}/api/v1/contests/${params.id}`, {
      next: { revalidate: 3600 }, // Cache pendant 1 heure
    })
    
    if (!response.ok) {
      throw new Error("Contest not found")
    }
    
    const contest = await response.json()
    
    if (!contest) {
      return createMetadata({
        title: englishTranslations.pages.contests.title, // Titre en anglais
        description: `Discover this contest on ${englishTranslations.siteName}`, // Description en anglais
        url: `/dashboard/contests/${params.id}`,
        language: lang,
      })
    }

    // Utiliser le nom du contest mais avec une description en anglais
    const title = `${contest.name || 'Contest'} - ${englishTranslations.siteName}`
    const description = contest.description 
      ? contest.description 
      : `Participate in the contest ${contest.name || 'this contest'} on ${englishTranslations.siteName}. Vote for your favorites and win prizes!`
    let image = contest.cover_image_url || contest.image_url || `${appUrl}/thumbnails.png`
    // S'assurer que l'image est une URL absolue
    if (!image.startsWith('http')) {
      image = image.startsWith('/') ? `${appUrl}${image}` : `${appUrl}/${image}`
    }

    return createMetadata({
      title, // Titre avec nom du contest
      description, // Description en anglais
      image,
      url: `/dashboard/contests/${params.id}`,
      type: "article",
      language: lang,
    })
  } catch (error) {
    console.error("Error generating metadata for contest:", error)
    return createMetadata({
      title: englishTranslations.pages.contests.title, // Titre en anglais
      description: `Discover this contest on ${englishTranslations.siteName}`, // Description en anglais
      url: `/dashboard/contests/${params.id}`,
      language: lang,
    })
  }
}

export default function ContestLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}

