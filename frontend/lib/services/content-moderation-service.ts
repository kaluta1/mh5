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

export interface AudioModerationResult {
  isApproved: boolean
  confidence: number
  flags: ContentFlag[]
  transcript?: string
  contentSafety?: {
    hate_speech: number
    profanity: number
    violence: number
    sensitive_content: number
  }
}

export interface VoiceOwnershipResult {
  isMatch: boolean
  confidence: number
  voiceDetected: boolean
  speechDuration?: number
  matchDetails?: {
    similarity: number
    referenceVoiceId?: string
  }
}

// Configuration - Sightengine (utilisé pour images/vidéos)
const SIGHTENGINE_API_USER = process.env.SLIGTHENGINE_API_USER || ''
const SIGHTENGINE_API_SECRET = process.env.SLIGTHENGINE_API_KEY || ''

// Configuration - AssemblyAI (utilisé pour audio)
const ASSEMBLYAI_API_KEY = process.env.ASSEMBLYAI_API_KEY || ''

// Seuils de modération (ajustables)
const MODERATION_THRESHOLDS = {
  nudity: 0.6,        // Score au-delà duquel le contenu est considéré adulte
  violence: 0.6,      // Score au-delà duquel le contenu est considéré violent
  gore: 0.4,          // Score pour gore/cadavres/sang
  weapons: 0.6,       // Score pour armes
  offensive: 0.6,     // Score pour contenu offensant
  drugs: 0.6,         // Score pour drogues
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
 * Analyse un fichier audio avec AssemblyAI
 * Transcrit l'audio et vérifie le contenu
 */
export async function moderateAudio(audioUrl: string): Promise<AudioModerationResult> {
  if (!ASSEMBLYAI_API_KEY) {
    console.warn('AssemblyAI API key not configured, skipping audio moderation')
    return {
      isApproved: true,
      confidence: 0,
      flags: []
    }
  }

  try {
    // 1. Soumettre l'audio pour transcription avec content safety
    const submitResponse = await fetch('https://api.assemblyai.com/v2/transcript', {
      method: 'POST',
      headers: {
        'Authorization': ASSEMBLYAI_API_KEY,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        audio_url: audioUrl,
        content_safety: true,           // Activer la détection de contenu sensible
        content_safety_confidence: 50,  // Seuil de confiance (0-100)
        speech_threshold: 0.2           // Seuil de détection de parole
      })
    })

    if (!submitResponse.ok) {
      throw new Error(`AssemblyAI submit error: ${submitResponse.status}`)
    }

    const submitData = await submitResponse.json()
    const transcriptId = submitData.id

    // 2. Poll pour le résultat (max 60 secondes)
    const result = await pollAudioTranscript(transcriptId)
    return processAudioModerationResult(result)

  } catch (error) {
    console.error('Audio moderation error:', error)
    return {
      isApproved: true,
      confidence: 0,
      flags: []
    }
  }
}

/**
 * Poll pour le résultat de transcription audio
 */
async function pollAudioTranscript(transcriptId: string, maxAttempts = 20): Promise<any> {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(resolve => setTimeout(resolve, 3000)) // Attendre 3 secondes

    try {
      const response = await fetch(
        `https://api.assemblyai.com/v2/transcript/${transcriptId}`,
        {
          headers: { 'Authorization': ASSEMBLYAI_API_KEY }
        }
      )

      const data = await response.json()
      
      if (data.status === 'completed') {
        return data
      } else if (data.status === 'error') {
        throw new Error(data.error || 'Transcription failed')
      }
      // Continue polling if status is 'queued' or 'processing'
    } catch (error) {
      console.error('Audio polling error:', error)
    }
  }

  throw new Error('Audio transcription timeout')
}

/**
 * Traite le résultat de modération audio
 */
function processAudioModerationResult(data: any): AudioModerationResult {
  const flags: ContentFlag[] = []
  let isApproved = true
  let maxConfidence = 0

  // Vérifier les résultats de content safety
  if (data.content_safety_labels && data.content_safety_labels.results) {
    for (const result of data.content_safety_labels.results) {
      for (const label of result.labels || []) {
        const confidence = label.confidence || 0
        
        // Map AssemblyAI labels to our flag types
        if (label.label === 'hate_speech' && confidence > 0.5) {
          isApproved = false
          maxConfidence = Math.max(maxConfidence, confidence)
          flags.push({
            type: 'hate',
            severity: confidence > 0.8 ? 'high' : 'medium',
            confidence,
            description: 'Discours haineux détecté'
          })
        }
        
        if (label.label === 'profanity' && confidence > 0.6) {
          maxConfidence = Math.max(maxConfidence, confidence)
          flags.push({
            type: 'offensive',
            severity: confidence > 0.8 ? 'high' : 'medium',
            confidence,
            description: 'Langage vulgaire détecté'
          })
          // Profanity léger ne bloque pas forcément
          if (confidence > 0.8) {
            isApproved = false
          }
        }
        
        if ((label.label === 'violence' || label.label === 'threats') && confidence > 0.5) {
          isApproved = false
          maxConfidence = Math.max(maxConfidence, confidence)
          flags.push({
            type: 'violence',
            severity: confidence > 0.8 ? 'high' : 'medium',
            confidence,
            description: 'Contenu violent ou menaces détectées'
          })
        }
        
        if (label.label === 'self_harm' && confidence > 0.5) {
          isApproved = false
          maxConfidence = Math.max(maxConfidence, confidence)
          flags.push({
            type: 'selfharm',
            severity: 'high',
            confidence,
            description: 'Contenu d\'automutilation détecté'
          })
        }
        
        if (label.label === 'sensitive_content' && confidence > 0.6) {
          maxConfidence = Math.max(maxConfidence, confidence)
          flags.push({
            type: 'offensive',
            severity: 'medium',
            confidence,
            description: 'Contenu sensible détecté'
          })
        }
      }
    }
  }

  // Extraire les scores de sécurité globaux
  const summaryLabels = data.content_safety_labels?.summary || {}

  return {
    isApproved,
    confidence: maxConfidence || 1,
    flags,
    transcript: data.text,
    contentSafety: {
      hate_speech: summaryLabels.hate_speech || 0,
      profanity: summaryLabels.profanity || 0,
      violence: summaryLabels.violence || 0,
      sensitive_content: summaryLabels.sensitive_content || 0
    }
  }
}

/**
 * Vérifie l'ownership d'un audio (comparaison vocale)
 * Compare l'empreinte vocale avec une référence
 */
export async function verifyVoiceOwnership(
  referenceAudioUrl: string,
  uploadedAudioUrl: string
): Promise<VoiceOwnershipResult> {
  // NOTE: La comparaison vocale nécessite un service spécialisé comme:
  // - Azure Speaker Recognition
  // - Amazon Voice ID
  // - Nuance Voice Biometrics
  // 
  // Pour l'instant, on implémente une vérification basique:
  // - On transcrit les deux audios
  // - On vérifie qu'il y a de la parole dans les deux
  // - La vraie comparaison vocale sera ajoutée ultérieurement
  
  if (!ASSEMBLYAI_API_KEY) {
    console.warn('AssemblyAI API key not configured, voice verification disabled')
    return {
      isMatch: true,
      confidence: 0,
      voiceDetected: false
    }
  }

  try {
    // Vérifier que l'audio uploadé contient de la parole
    const submitResponse = await fetch('https://api.assemblyai.com/v2/transcript', {
      method: 'POST',
      headers: {
        'Authorization': ASSEMBLYAI_API_KEY,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        audio_url: uploadedAudioUrl,
        speech_threshold: 0.2
      })
    })

    if (!submitResponse.ok) {
      throw new Error(`AssemblyAI submit error: ${submitResponse.status}`)
    }

    const submitData = await submitResponse.json()
    const result = await pollAudioTranscript(submitData.id)

    // Vérifier la durée de parole
    const speechDuration = result.audio_duration || 0
    const hasVoice = result.text && result.text.length > 10

    if (!hasVoice) {
      return {
        isMatch: false,
        confidence: 0,
        voiceDetected: false,
        speechDuration,
        matchDetails: {
          similarity: 0
        }
      }
    }

    // TODO: Implémenter la vraie comparaison vocale avec un service biométrique
    // Pour l'instant, on accepte si une voix est détectée
    return {
      isMatch: true,
      confidence: 0.5, // Confiance moyenne car pas de vraie comparaison
      voiceDetected: true,
      speechDuration,
      matchDetails: {
        similarity: 0.5
      }
    }

  } catch (error) {
    console.error('Voice ownership verification error:', error)
    return {
      isMatch: true,
      confidence: 0,
      voiceDetected: false
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
 * Modère le contenu (image, vidéo ou audio) et vérifie l'ownership
 */
export async function moderateAndVerifyContent(
  contentUrl: string,
  contentType: 'image' | 'video' | 'audio',
  verificationUrl?: string
): Promise<{
  moderation: ModerationResult | AudioModerationResult
  ownership?: OwnershipVerificationResult
  voiceOwnership?: VoiceOwnershipResult
}> {
  // Modération du contenu selon le type
  let moderation: ModerationResult | AudioModerationResult

  switch (contentType) {
    case 'image':
      moderation = await moderateImage(contentUrl)
      break
    case 'video':
      moderation = await moderateVideo(contentUrl)
      break
    case 'audio':
      moderation = await moderateAudio(contentUrl)
      break
  }

  // Vérification d'ownership si une URL de vérification est fournie
  let ownership: OwnershipVerificationResult | undefined
  let voiceOwnership: VoiceOwnershipResult | undefined

  if (verificationUrl) {
    if (contentType === 'image') {
      ownership = await verifyOwnership(verificationUrl, contentUrl)
    } else if (contentType === 'audio') {
      voiceOwnership = await verifyVoiceOwnership(verificationUrl, contentUrl)
    }
  }

  return { moderation, ownership, voiceOwnership }
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
