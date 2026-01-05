/**
 * Cache pour éviter de re-uploader les fichiers déjà uploadés
 * Utilise le hash SHA-256 du fichier comme clé
 */

const CACHE_KEY = 'uploadthing_file_cache'
const CACHE_MAX_AGE = 7 * 24 *365* 60 * 60 * 1000 // 1 an

interface CachedFile {
  url: string
  name: string
  size: number
  type: string
  hash: string
  uploadedAt: number
}

interface FileCache {
  files: Record<string, CachedFile>
}

/**
 * Calcule le hash SHA-256 d'un fichier
 */
export async function calculateFileHash(file: File): Promise<string> {
  const arrayBuffer = await file.arrayBuffer()
  const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
}

/**
 * Récupère le cache depuis localStorage
 */
function getCache(): FileCache {
  if (typeof window === 'undefined') return { files: {} }
  
  try {
    const cached = localStorage.getItem(CACHE_KEY)
    if (cached) {
      const cache = JSON.parse(cached) as FileCache
      // Nettoyer les entrées expirées
      const now = Date.now()
      const validFiles: Record<string, CachedFile> = {}
      
      for (const [hash, file] of Object.entries(cache.files)) {
        if (now - file.uploadedAt < CACHE_MAX_AGE) {
          validFiles[hash] = file
        }
      }
      
      return { files: validFiles }
    }
  } catch (e) {
    console.warn('Error reading file cache:', e)
  }
  
  return { files: {} }
}

/**
 * Sauvegarde le cache dans localStorage
 */
function saveCache(cache: FileCache): void {
  if (typeof window === 'undefined') return
  
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(cache))
  } catch (e) {
    console.warn('Error saving file cache:', e)
  }
}

/**
 * Vérifie si un fichier existe déjà dans le cache
 */
export async function getCachedFile(file: File): Promise<CachedFile | null> {
  const hash = await calculateFileHash(file)
  const cache = getCache()
  
  const cached = cache.files[hash]
  if (cached) {
    console.log('📦 Fichier trouvé dans le cache:', cached.url)
    return cached
  }
  
  return null
}

/**
 * Ajoute un fichier au cache
 */
export function addToCache(file: File, url: string, hash: string): void {
  const cache = getCache()
  
  cache.files[hash] = {
    url,
    name: file.name,
    size: file.size,
    type: file.type,
    hash,
    uploadedAt: Date.now()
  }
  
  saveCache(cache)
  console.log('💾 Fichier ajouté au cache:', url)
}

/**
 * Supprime un fichier du cache
 */
export function removeFromCache(hash: string): void {
  const cache = getCache()
  delete cache.files[hash]
  saveCache(cache)
}

/**
 * Vide tout le cache
 */
export function clearCache(): void {
  if (typeof window === 'undefined') return
  localStorage.removeItem(CACHE_KEY)
  console.log('🗑️ Cache vidé')
}

/**
 * Retourne les statistiques du cache
 */
export function getCacheStats(): { count: number; totalSize: number } {
  const cache = getCache()
  const files = Object.values(cache.files)
  
  return {
    count: files.length,
    totalSize: files.reduce((acc, f) => acc + f.size, 0)
  }
}
