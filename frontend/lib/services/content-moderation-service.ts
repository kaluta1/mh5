/**
 * Service de modération et vérification de contenu
 * Utilise Sightengine pour la modération et Google Vision pour la comparaison
 */

// Types pour les résultats de modération
export interface ModerationResult {
  isApproved: boolean
  confidence: number
  flags: ContentFlag[]
  details: ModerationDetails
}

export interface ContentFlag {
  type: 'adult' | 'violence' | 'gore' | 'weapons' | 'drugs' | 'hate' | 'selfharm' | 'offensive'
  severity: 'low' | 'medium' | 'high'
  confidence: number
  description: string
}

export interface ModerationDetails {
  nudity?: { score: number; partial: number; explicit: number }
  violence?: { score: number; gore: number; weapons: number }
  offensive?: { score: number }
  scam?: { score: number }
  text?: { profanity: boolean; offensive: boolean }
}

export interface OwnershipVerificationResult {
  isMatch: boolean
  confidence: number
  faceDetected: boolean
  matchDetails?: {
    similarity: number
    verificationImageFaces: number
    uploadedImageFaces: number
  }
}

// Configuration - Sightengine (utilisé pour tout: modération + ownership)
const SIGHTENGINE_API_USER = process.env.SLIGTHENGINE_API_USER || ''
const SIGHTENGINE_API_SECRET = process.env.SLIGTHENGINE_API_KEY || ''

// Seuils de modération (ajustables)
const MODERATION_THRESHOLDS = {
  nudity: 0.6,        // Score au-delà duquel le contenu est considéré adulte
  violence: 0.7,      // Score au-delà duquel le contenu est considéré violent
  gore: 0.5,          // Score pour gore/cadavres/sang
  weapons: 0.8,       // Score pour armes
  offensive: 0.7,     // Score pour contenu offensant
  drugs: 0.8,         // Score pour drogues
}

/**
 * Analyse une image avec Sightengine
 */
export async function moderateImage(imageUrl: string): Promise<ModerationResult> {
  // Si pas de clés API, retourner un résultat par défaut (mode dev)
  if (!SIGHTENGINE_API_USER || !SIGHTENGINE_API_SECRET) {
    console.warn('Sightengine API keys not configured, skipping moderation')
    return {
      isApproved: true,
      confidence: 0,
      flags: [],
      details: {}
    }
  }

  try {
    const response = await fetch(
      `https://api.sightengine.com/1.0/check.json?` +
      `url=${encodeURIComponent(imageUrl)}` +
      `&models=nudity-2.0,violence,gore,weapon,offensive,scam` +
      `&api_user=${SIGHTENGINE_API_USER}` +
      `&api_secret=${SIGHTENGINE_API_SECRET}`
    )

    if (!response.ok) {
      throw new Error(`Sightengine API error: ${response.status}`)
    }

    const data = await response.json()
    return processSightengineResponse(data)
  } catch (error) {
    console.error('Image moderation error:', error)
    // En cas d'erreur, on approuve par défaut mais avec confidence 0
    return {
      isApproved: true,
      confidence: 0,
      flags: [],
      details: {}
    }
  }
}

/**
 * Analyse une vidéo avec Sightengine (analyse des frames)
 */
export async function moderateVideo(videoUrl: string): Promise<ModerationResult> {
  if (!SIGHTENGINE_API_USER || !SIGHTENGINE_API_SECRET) {
    console.warn('Sightengine API keys not configured, skipping moderation')
    return {
      isApproved: true,
      confidence: 0,
      flags: [],
      details: {}
    }
  }

  try {
    // Sightengine Video moderation - async job
    const response = await fetch(
      `https://api.sightengine.com/1.0/video/check.json`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          stream_url: videoUrl,
          models: 'nudity-2.0,violence,gore,weapon,offensive',
          api_user: SIGHTENGINE_API_USER,
          api_secret: SIGHTENGINE_API_SECRET,
          callback_url: '', // Optionnel: URL de callback
          interval: '1.0'   // Analyse toutes les secondes
        })
      }
    )

    if (!response.ok) {
      throw new Error(`Sightengine Video API error: ${response.status}`)
    }

    const data = await response.json()
    
    // Pour les vidéos, on doit attendre le traitement
    // En production, utiliser un webhook callback
    // Pour l'instant, on fait une analyse simplifiée
    if (data.status === 'success' && data.request) {
      // Polling pour attendre le résultat (max 30 secondes)
      return await pollVideoResult(data.request.id)
    }

    return {
      isApproved: true,
      confidence: 0,
      flags: [],
      details: {}
    }
  } catch (error) {
    console.error('Video moderation error:', error)
    return {
      isApproved: true,
      confidence: 0,
      flags: [],
      details: {}
    }
  }
}

/**
 * Poll pour le résultat d'analyse vidéo
 */
async function pollVideoResult(requestId: string, maxAttempts = 10): Promise<ModerationResult> {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(resolve => setTimeout(resolve, 3000)) // Attendre 3 secondes

    try {
      const response = await fetch(
        `https://api.sightengine.com/1.0/video/check.json?` +
        `id=${requestId}` +
        `&api_user=${SIGHTENGINE_API_USER}` +
        `&api_secret=${SIGHTENGINE_API_SECRET}`
      )

      const data = await response.json()
      
      if (data.status === 'finished') {
        return processVideoModerationResponse(data)
      }
    } catch (error) {
      console.error('Video polling error:', error)
    }
  }

  // Timeout - approuver par défaut
  return {
    isApproved: true,
    confidence: 0,
    flags: [],
    details: {}
  }
}

/**
 * Traite la réponse de Sightengine pour les images
 */
function processSightengineResponse(data: any): ModerationResult {
  const flags: ContentFlag[] = []
  let isApproved = true

  // Vérifier la nudité
  if (data.nudity) {
    const nudityScore = Math.max(
      data.nudity.sexual_activity || 0,
      data.nudity.sexual_display || 0,
      data.nudity.erotica || 0
    )
    if (nudityScore > MODERATION_THRESHOLDS.nudity) {
      isApproved = false
      flags.push({
        type: 'adult',
        severity: nudityScore > 0.8 ? 'high' : 'medium',
        confidence: nudityScore,
        description: 'Contenu adulte détecté'
      })
    }
  }

  // Vérifier la violence
  if (data.violence) {
    const violenceScore = data.violence.prob || 0
    if (violenceScore > MODERATION_THRESHOLDS.violence) {
      isApproved = false
      flags.push({
        type: 'violence',
        severity: violenceScore > 0.85 ? 'high' : 'medium',
        confidence: violenceScore,
        description: 'Contenu violent détecté'
      })
    }
  }

  // Vérifier le gore (sang, cadavres)
  if (data.gore) {
    const goreScore = data.gore.prob || 0
    if (goreScore > MODERATION_THRESHOLDS.gore) {
      isApproved = false
      flags.push({
        type: 'gore',
        severity: goreScore > 0.7 ? 'high' : 'medium',
        confidence: goreScore,
        description: 'Contenu gore/sanglant détecté'
      })
    }
  }

  // Vérifier les armes
  if (data.weapon) {
    const weaponScore = data.weapon.prob || 0
    if (weaponScore > MODERATION_THRESHOLDS.weapons) {
      isApproved = false
      flags.push({
        type: 'weapons',
        severity: 'medium',
        confidence: weaponScore,
        description: 'Arme détectée'
      })
    }
  }

  // Vérifier le contenu offensant
  if (data.offensive) {
    const offensiveScore = data.offensive.prob || 0
    if (offensiveScore > MODERATION_THRESHOLDS.offensive) {
      isApproved = false
      flags.push({
        type: 'offensive',
        severity: 'medium',
        confidence: offensiveScore,
        description: 'Contenu offensant détecté'
      })
    }
  }

  return {
    isApproved,
    confidence: flags.length > 0 ? Math.max(...flags.map(f => f.confidence)) : 1,
    flags,
    details: {
      nudity: data.nudity,
      violence: data.violence,
      offensive: data.offensive,
      scam: data.scam
    }
  }
}

/**
 * Traite la réponse de modération vidéo
 */
function processVideoModerationResponse(data: any): ModerationResult {
  const flags: ContentFlag[] = []
  let isApproved = true
  let maxConfidence = 0

  // Parcourir les frames analysées
  if (data.frames && Array.isArray(data.frames)) {
    for (const frame of data.frames) {
      const frameResult = processSightengineResponse(frame)
      if (!frameResult.isApproved) {
        isApproved = false
        flags.push(...frameResult.flags)
        maxConfidence = Math.max(maxConfidence, frameResult.confidence)
      }
    }
  }

  // Dédupliquer les flags
  const uniqueFlags = flags.reduce((acc, flag) => {
    const existing = acc.find(f => f.type === flag.type)
    if (!existing || existing.confidence < flag.confidence) {
      return [...acc.filter(f => f.type !== flag.type), flag]
    }
    return acc
  }, [] as ContentFlag[])

  return {
    isApproved,
    confidence: maxConfidence || 1,
    flags: uniqueFlags,
    details: {}
  }
}

/**
 * Vérifie si le visage de l'image uploadée correspond au visage de vérification
 * Utilise Sightengine Face Comparison API
 */
export async function verifyOwnership(
  verificationImageUrl: string,
  uploadedImageUrl: string
): Promise<OwnershipVerificationResult> {
  // Si pas de clé API Sightengine
  if (!SIGHTENGINE_API_USER || !SIGHTENGINE_API_SECRET) {
    console.warn('Sightengine API keys not configured, ownership verification disabled')
    return {
      isMatch: true,
      confidence: 0,
      faceDetected: false
    }
  }

  try {
    // Utiliser Sightengine Face Comparison API
    const response = await fetch(
      `https://api.sightengine.com/1.0/face/check.json`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          url: uploadedImageUrl,
          reference_url: verificationImageUrl,
          api_user: SIGHTENGINE_API_USER,
          api_secret: SIGHTENGINE_API_SECRET
        })
      }
    )

    if (!response.ok) {
      throw new Error(`Sightengine API error: ${response.status}`)
    }

    const data = await response.json()
    
    console.log('Face comparison result:', data)

    // Vérifier si des visages ont été détectés
    if (data.status !== 'success') {
      console.warn('Face comparison failed:', data)
      return {
        isMatch: true,
        confidence: 0,
        faceDetected: false
      }
    }

    // Analyser le résultat
    const faces = data.faces || []
    const referenceFaces = data.reference_faces || []
    
    if (faces.length === 0) {
      return {
        isMatch: true,
        confidence: 0,
        faceDetected: false,
        matchDetails: {
          similarity: 0,
          verificationImageFaces: referenceFaces.length,
          uploadedImageFaces: 0
        }
      }
    }

    if (referenceFaces.length === 0) {
      return {
        isMatch: false,
        confidence: 0,
        faceDetected: true,
        matchDetails: {
          similarity: 0,
          verificationImageFaces: 0,
          uploadedImageFaces: faces.length
        }
      }
    }

    // Trouver la meilleure correspondance
    let bestMatch = 0
    for (const face of faces) {
      if (face.match && face.match.similarity) {
        bestMatch = Math.max(bestMatch, face.match.similarity)
      }
    }

    const similarity = bestMatch
    const SIMILARITY_THRESHOLD = 0.7 // 70% de similarité requise

    return {
      isMatch: similarity >= SIMILARITY_THRESHOLD,
      confidence: similarity,
      faceDetected: true,
      matchDetails: {
        similarity,
        verificationImageFaces: referenceFaces.length,
        uploadedImageFaces: faces.length
      }
    }
  } catch (error) {
    console.error('Ownership verification error:', error)
    return {
      isMatch: true,
      confidence: 0,
      faceDetected: false
    }
  }
}

/**
 * Détecte les visages dans une image avec Sightengine
 */
async function detectFaces(imageUrl: string): Promise<any[]> {
  if (!SIGHTENGINE_API_USER || !SIGHTENGINE_API_SECRET) {
    return []
  }

  try {
    const response = await fetch(
      `https://api.sightengine.com/1.0/check.json?` +
      `url=${encodeURIComponent(imageUrl)}` +
      `&models=face-attributes` +
      `&api_user=${SIGHTENGINE_API_USER}` +
      `&api_secret=${SIGHTENGINE_API_SECRET}`
    )

    const data = await response.json()
    return data.faces || []
  } catch (error) {
    console.error('Face detection error:', error)
    return []
  }
}

/**
 * Modère le contenu (image ou vidéo) et vérifie l'ownership
 */
export async function moderateAndVerifyContent(
  contentUrl: string,
  contentType: 'image' | 'video',
  verificationImageUrl?: string
): Promise<{
  moderation: ModerationResult
  ownership?: OwnershipVerificationResult
}> {
  // Modération du contenu
  const moderation = contentType === 'image'
    ? await moderateImage(contentUrl)
    : await moderateVideo(contentUrl)

  // Vérification d'ownership si une image de vérification est fournie
  let ownership: OwnershipVerificationResult | undefined
  if (verificationImageUrl && contentType === 'image') {
    ownership = await verifyOwnership(verificationImageUrl, contentUrl)
  }

  return { moderation, ownership }
}

/**
 * Supprime un fichier d'Uploadthing si la modération échoue
 */
export async function deleteUploadthingFile(fileKey: string): Promise<boolean> {
  const UPLOADTHING_SECRET = process.env.UPLOADTHING_SECRET

  if (!UPLOADTHING_SECRET) {
    console.error('UPLOADTHING_SECRET not configured')
    return false
  }

  try {
    const response = await fetch('https://uploadthing.com/api/deleteFile', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Uploadthing-Api-Key': UPLOADTHING_SECRET
      },
      body: JSON.stringify({ fileKeys: [fileKey] })
    })

    return response.ok
  } catch (error) {
    console.error('Error deleting file:', error)
    return false
  }
}
