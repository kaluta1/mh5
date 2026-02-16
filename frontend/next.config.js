/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable compression
  compress: true,

  // Optimize production builds
  swcMinify: true,

  // Enable React strict mode for better performance
  reactStrictMode: true,

  // Optimize images
  images: {
    remotePatterns: [
      {
        protocol: 'http',
        hostname: 'localhost',
        port: '8000',
        pathname: '/media/**',
      },
      {
        protocol: 'https',
        hostname: 'localhost',
        port: '8000',
        pathname: '/media/**',
      },
      {
        protocol: 'http',
        hostname: '127.0.0.1',
        port: '8000',
        pathname: '/media/**',
      },
      {
        protocol: 'https',
        hostname: '*.onrender.com',
        pathname: '/media/**',
      },
      {
        protocol: 'https',
        hostname: 'zlz3wbxsni.ufs.sh',
        pathname: '/**',
      },
      {
        protocol: 'https',
        hostname: 'utfs.io',
        pathname: '/**',
      },
    ],
    unoptimized: false,
    formats: ['image/avif', 'image/webp'],
    deviceSizes: [640, 750, 828, 1080, 1200, 1920, 2048, 3840],
    imageSizes: [16, 32, 48, 64, 96, 128, 256, 384],
  },

  // Optimize bundle size
  // Note: optimizeCss requires 'critters' package, disabled for now
  // experimental: {
  //   optimizeCss: true,
  // },

  // Webpack: use Next default optimization to avoid high memory during build (Array buffer allocation failed)
  // Custom splitChunks was removed to reduce memory pressure; Next.js defaults are sufficient.
  webpack: (config) => config,

  async headers() {
    return [
      {
        source: '/.well-known/assetlinks.json',
        headers: [
          {
            key: 'Content-Type',
            value: 'application/json',
          },
        ],
      },
    ];
  },
  async rewrites() {
    // Share link rewrites: backend URL from env or default (see lib/config.ts)
    const backendUrl = (process.env.NEXT_PUBLIC_API_URL || 'https://mh5-hbjp.onrender.com').replace(/\/+$/, '')

    return [
      {
        source: '/s/c/:id',
        destination: `${backendUrl}/api/v1/share/c/:id`,
      },
      {
        source: '/s/p/:username',
        destination: `${backendUrl}/api/v1/share/p/:username`,
      },
      {
        source: '/s/r/:code',
        destination: `${backendUrl}/api/v1/share/r/:code`,
      },
      {
        source: '/s/r',
        destination: `${backendUrl}/api/v1/share/r`,
      },
    ];
  },

  // IMPORTANT: To fix Vercel deployment stack overflow error:
  // 1. Go to Vercel Dashboard → Your Project → Settings → General
  // 2. Set "Root Directory" to: frontend
  // 3. Save and redeploy
  //
  // This prevents Vercel from scanning the backend directory during build

}

module.exports = nextConfig
