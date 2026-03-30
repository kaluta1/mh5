import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "./globals.css"
import "react-quill/dist/quill.snow.css"
import { ThemeProvider } from "@/components/theme-provider"
import { AuthProvider } from "@/hooks/use-auth"
import { LanguageProvider } from "@/contexts/language-context"
import { ToastProvider } from "@/components/ui/toast"
import { CookieConsent } from "@/components/ui/cookie-consent"
import { ErrorBoundary } from "@/components/error-boundary"
import { ReownAppKitProvider } from "@/components/reown-appkit-provider"
import { getMetadataTranslations, detectLanguageFromHeaders, getKeywords } from "@/lib/metadata-translations"
import { headers } from "next/headers"


// Optimize font loading
const inter = Inter({
  subsets: ["latin"],
  display: 'swap', // Better font loading performance
  preload: true,
  fallback: ['system-ui', 'arial']
})

const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://myhigh5.com"
const defaultImage = `${appUrl}/thumbnails.png` // Image par défaut pour le partage

// Générer les métadonnées selon la langue détectée
export async function generateMetadata(): Promise<Metadata> {
  let lang: import("@/lib/translations").Language = 'en'
  try {
    const headersList = headers()
    lang = detectLanguageFromHeaders(headersList)
  } catch {
    // Si headers() n'est pas disponible, utiliser le défaut
    lang = 'en'
  }

  const translations = getMetadataTranslations(lang)
  // Traductions en anglais pour les partages sociaux (toujours en anglais)
  const englishTranslations = getMetadataTranslations('en')

  // Utiliser directement l'image par défaut (pas d'appel API bloquant)
  const absoluteOgImage = defaultImage

  // Utiliser les traductions en anglais pour tous les partages sociaux
  const englishTitle = englishTranslations.pages.home.title
  const englishDescription = englishTranslations.pages.home.description || englishTranslations.defaultDescription || 'Join contests, build your network, and earn through our 10-level affiliate program. Every vote, every referral generates income.'

  return {
    metadataBase: new URL(appUrl),
    title: {
      default: translations.pages.home.title,
      template: `%s | ${translations.siteName}`
    },
    description: translations.pages.home.description,
    keywords: getKeywords(lang),
    authors: [{ name: `${translations.siteName} Team` }],
    creator: translations.siteName,
    publisher: translations.siteName,
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        'max-video-preview': -1,
        'max-image-preview': 'large',
        'max-snippet': -1,
      },
    },
    openGraph: {
      type: "website",
      locale: "en_US", // Toujours en anglais pour les partages
      url: appUrl,
      siteName: englishTranslations.siteName,
      title: englishTitle,
      description: englishDescription,
      images: [
        {
          url: absoluteOgImage,
          width: 1200,
          height: 630,
          alt: englishTitle,
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: englishTitle,
      description: englishDescription,
      images: [absoluteOgImage],
      creator: "@high5",
    },
    alternates: {
      canonical: appUrl,
    },
    icons: {
      icon: [
        { url: '/thumbnails.png', sizes: 'any' },
        { url: '/thumbnails.png', type: 'image/png' },
      ],
      apple: [
        { url: '/thumbnails.png', sizes: '180x180', type: 'image/png' },
      ],
      shortcut: '/thumbnails.png',
    },
  }
}


export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Détecter la langue pour l'attribut lang du HTML
  let htmlLang = 'en'
  try {
    const headersList = headers()
    htmlLang = detectLanguageFromHeaders(headersList)
  } catch {
    htmlLang = 'en'
  }

  return (
    <html lang={htmlLang} suppressHydrationWarning>
      <head>
        {/* Preconnect to API for faster requests */}
        <link rel="preconnect" href={process.env.NEXT_PUBLIC_API_URL || 'https://mh5-hbjp.onrender.com'} crossOrigin="anonymous" />
        {/* DNS prefetch for external resources */}
        <link rel="dns-prefetch" href="https://fonts.googleapis.com" />
        <link rel="dns-prefetch" href="https://fonts.gstatic.com" />
      </head>
      <body className={inter.className}>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              // Initialize performance optimizations immediately
              (function() {
                if (typeof window === 'undefined') return;
                // Preconnect to API
                const apiUrl = '${process.env.NEXT_PUBLIC_API_URL || 'https://mh5-hbjp.onrender.com'}';
                const link = document.createElement('link');
                link.rel = 'preconnect';
                link.href = apiUrl;
                link.crossOrigin = 'anonymous';
                document.head.appendChild(link);
                // Setup link prefetching
                document.addEventListener('DOMContentLoaded', function() {
                  const links = document.querySelectorAll('a[href]');
                  links.forEach(function(link) {
                    const href = link.getAttribute('href');
                    if (href && !href.startsWith('#') && !href.startsWith('mailto:') && !href.startsWith('tel:')) {
                      link.addEventListener('mouseenter', function() {
                        const prefetchLink = document.createElement('link');
                        prefetchLink.rel = 'prefetch';
                        prefetchLink.href = href;
                        document.head.appendChild(prefetchLink);
                      }, { once: true });
                    }
                  });
                });
              })();
            `,
          }}
        />
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <ErrorBoundary>
            <ToastProvider>
              <ReownAppKitProvider>
                <LanguageProvider>
                  <AuthProvider>
                    {children}
                    <CookieConsent />
                  </AuthProvider>
                </LanguageProvider>
              </ReownAppKitProvider>
            </ToastProvider>
          </ErrorBoundary>
        </ThemeProvider>
      </body>
    </html>
  )
}
