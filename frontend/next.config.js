/** @type {import('next').NextConfig} */
const nextVersion = (() => {
  try {
    // next.config.js is evaluated by Node, so we can read Next's version at runtime.
    // This keeps the config compatible with both Next 14 (no `turbopack` key)
    // and Next 16+ (where Turbopack is enabled by default).
    return require('next/package.json')?.version || ''
  } catch {
    return ''
  }
})()

const nextMajor = Number(String(nextVersion).split('.')[0] || 0)
const turbopackConfig = nextMajor >= 16 ? { turbopack: {} } : {}

const nextConfig = {
  ...turbopackConfig,

  // Enable compression
  compress: true,

  // Optimize production builds
  // Enable React strict mode for better performance
  reactStrictMode: true,

  // Performance optimizations
  poweredByHeader: false, // Remove X-Powered-By header
  generateEtags: true, // Enable ETags for better caching
  
  // Experimental features for performance
  experimental: {
    optimizePackageImports: ['lucide-react', '@radix-ui/react-icons'], // Tree-shake unused icons
  },

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

  // Webpack: Optimize for performance
  webpack: (config, { isServer }) => {
    // Optimize bundle splitting
    if (!isServer) {
      config.optimization = {
        ...config.optimization,
        splitChunks: {
          chunks: 'all',
          cacheGroups: {
            default: false,
            vendors: false,
            // Vendor chunk for large libraries
            vendor: {
              name: 'vendor',
              chunks: 'all',
              test: /node_modules/,
              priority: 20,
            },
            // Common chunk for shared code
            common: {
              name: 'common',
              minChunks: 2,
              chunks: 'all',
              priority: 10,
              reuseExistingChunk: true,
            },
          },
        },
      }
    }
    return config
  },

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
