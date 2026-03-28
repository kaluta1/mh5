import type { MetadataRoute } from 'next'

const appUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://myhigh5.com'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/maintenance'],
      },
    ],
    sitemap: `${appUrl}/sitemap.xml`,
    host: appUrl,
  }
}
