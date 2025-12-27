import { Metadata } from "next"
import { createMetadata } from "../metadata"
import { getMetadataTranslations, detectLanguageFromHeaders } from "@/lib/metadata-translations"
import { headers } from "next/headers"

function generateMetadata(): Metadata {
  const headersList = headers()
  const lang = detectLanguageFromHeaders(headersList)
  const translations = getMetadataTranslations(lang)

  return createMetadata({
    title: translations.pages.login.title,
    description: translations.pages.login.description,
    url: "/login",
    language: lang,
  })
}

export const metadata: Metadata = generateMetadata()

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <>{children}</>
}

