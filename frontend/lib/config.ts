/**
 * Configuration de l'application frontend
 */

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://mh5-hbjp.onrender.com'

export const config = {
  api: {
    url: API_URL,
    timeout: 30000,
    retries: 3
  },
  app: {
    name: 'MyHigh5',
    version: '1.0.0'
  }
}
