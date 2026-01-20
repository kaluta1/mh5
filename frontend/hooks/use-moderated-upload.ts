'use client'

import { useState, useCallback } from 'react'
import { getCachedFile, addToCache, calculateFileHash } from '@/lib/utils/file-cache'

interface UploadResult {
  url: string
  key?: string
  name: string
  size: number
  type: string
  fromCache?: boolean
}

interface ModerationFlag {
  type: string
  severity: string
  confidence: number
  description: string
}

interface UseModeratedUploadOptions {
  onSuccess?: (result: UploadResult) => void
  onError?: (error: string, flags?: ModerationFlag[]) => void
  onProgress?: (progress: number) => void
  verificationImageUrl?: string
  accessToken?: string
  maxSizeMB?: number
}

interface UploadState {
  isUploading: boolean
  progress: number
  error: string | null
  moderationFlags: ModerationFlag[]
}

export function useModeratedUpload(options: UseModeratedUploadOptions = {}) {
  const [state, setState] = useState<UploadState>({
    isUploading: false,
    progress: 0,
    error: null,
    moderationFlags: []
  })

  const upload = useCallback(async (file: File) => {
    setState({
      isUploading: true,
      progress: 0,
      error: null,
      moderationFlags: []
    })

    try {
      // ============================================
      // VÉRIFIER LA TAILLE DU FICHIER D'ABORD
      // ============================================
      if (options.maxSizeMB) {
        const maxSizeBytes = options.maxSizeMB * 1024 * 1024
        if (file.size > maxSizeBytes) {
          const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2)
          const errorMessage = `Le fichier est trop volumineux (${fileSizeMB}MB). Taille maximale autorisée: ${options.maxSizeMB}MB`
          
          setState({
            isUploading: false,
            progress: 0,
            error: errorMessage,
            moderationFlags: []
          })
          
          options.onError?.(errorMessage)
          return null
        }
      }

      // ============================================
      // VÉRIFIER LE CACHE
      // ============================================
      const cachedFile = await getCachedFile(file)
      if (cachedFile) {
        console.log('📦 Fichier déjà uploadé, utilisation du cache:', cachedFile.url)
        
        const result: UploadResult = {
          url: cachedFile.url,
          name: cachedFile.name,
          size: cachedFile.size,
          type: cachedFile.type,
          fromCache: true
        }

        setState({
          isUploading: false,
          progress: 100,
          error: null,
          moderationFlags: []
        })

        options.onSuccess?.(result)
        return result
      }

      // Calculer le hash pour le cache
      const fileHash = await calculateFileHash(file)

      // Créer le FormData
      const formData = new FormData()
      formData.append('file', file)
      
      if (options.verificationImageUrl) {
        formData.append('verificationImageUrl', options.verificationImageUrl)
      }

      // Simuler la progression
      setState(prev => ({ ...prev, progress: 10 }))
      options.onProgress?.(10)

      // Appeler l'API de modération + upload
      const response = await fetch('/api/upload/moderated', {
        method: 'POST',
        headers: {
          'x-access-token': options.accessToken || ''
        },
        body: formData
      })

      setState(prev => ({ ...prev, progress: 50 }))
      options.onProgress?.(50)

      const data = await response.json()

      if (!response.ok) {
        const errorMessage = data.details || data.error || 'Erreur lors de l\'upload'
        const flags = data.flags || []
        
        setState({
          isUploading: false,
          progress: 0,
          error: errorMessage,
          moderationFlags: flags
        })
        
        options.onError?.(errorMessage, flags)
        return null
      }

      setState(prev => ({ ...prev, progress: 100 }))
      options.onProgress?.(100)

      const result: UploadResult = {
        url: data.file.url,
        key: data.file.key,
        name: data.file.name,
        size: data.file.size,
        type: data.file.type,
        fromCache: false
      }

      // Ajouter au cache pour la prochaine fois
      addToCache(file, result.url, fileHash)

      setState({
        isUploading: false,
        progress: 100,
        error: null,
        moderationFlags: []
      })

      options.onSuccess?.(result)
      return result

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Erreur inconnue'
      
      setState({
        isUploading: false,
        progress: 0,
        error: errorMessage,
        moderationFlags: []
      })
      
      options.onError?.(errorMessage)
      return null
    }
  }, [options])

  const uploadMultiple = useCallback(async (files: File[]) => {
    const results: UploadResult[] = []
    
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      const progress = ((i + 1) / files.length) * 100
      
      setState(prev => ({ ...prev, progress }))
      options.onProgress?.(progress)
      
      const result = await upload(file)
      if (result) {
        results.push(result)
      } else {
        // Si une modération échoue, arrêter
        break
      }
    }
    
    return results
  }, [upload, options])

  const reset = useCallback(() => {
    setState({
      isUploading: false,
      progress: 0,
      error: null,
      moderationFlags: []
    })
  }, [])

  return {
    upload,
    uploadMultiple,
    reset,
    isUploading: state.isUploading,
    progress: state.progress,
    error: state.error,
    moderationFlags: state.moderationFlags
  }
}
