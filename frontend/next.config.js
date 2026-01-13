/** @type {import('next').NextConfig} */
const nextConfig = {
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
    domains: [
      'localhost',
      '127.0.0.1',
      'zlz3wbxsni.ufs.sh',
      'utfs.io',
    ],
    unoptimized: false,
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
    return [
      {
        source: '/s/c/:id',
        destination: 'https://mh5-sbe4.onrender.com/api/v1/share/c/:id',
      },
      {
        source: '/s/p/:username',
        destination: 'https://mh5-sbe4.onrender.com/api/v1/share/p/:username',
      },
      {
        source: '/s/r/:code',
        destination: 'https://mh5-sbe4.onrender.com/api/v1/share/r/:code',
      },
      {
        source: '/s/r',
        destination: 'https://mh5-sbe4.onrender.com/api/v1/share/r',
      },
    ];
  },

}

module.exports = nextConfig
