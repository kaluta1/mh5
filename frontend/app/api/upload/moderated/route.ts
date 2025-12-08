import { NextRequest, NextResponse } from 'next/server'
import { UTApi } from 'uploadthing/server'

// Configuration Sightengine
const SIGHTENGINE_API_USER = process.env.SLIGTHENGINE_API_USER || ''
const SIGHTENGINE_API_SECRET = process.env.SLIGTHENGINE_API_KEY || ''
const ENABLE_MODERATION = process.env.ENABLE_CONTENT_MODERATION === 'true'

// Seuils de modération
const MODERATION_THRESHOLDS = {
  nudity: 0.6,
  violence: 0.7,
  gore: 0.5,
  weapons: 0.8,
  offensive: 0.7,
}

interface ModerationFlag {
  type: string
  severity: string
  confidence: number
  description: string
}

/**
 * API pour upload avec modération AVANT stockage
 * POST /api/upload/moderated
 * Body: FormData avec 'file' et optionnel 'verificationImageUrl'
 */
export async function POST(request: NextRequest) {
  try {
    // Vérifier l'authentification
    const authHeader = request.headers.get('authorization')
    const accessToken = request.headers.get('x-access-token')
    
    if (!authHeader && !accessToken) {
      return NextResponse.json({ error: 'Non autorisé' }, { status: 401 })
    }

    // Vérifier le token avec le backend
    const token = authHeader?.replace('Bearer ', '') || accessToken
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    
    const authResponse = await fetch(`${apiUrl}/api/v1/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    
    if (!authResponse.ok) {
      return NextResponse.json({ error: 'Token invalide' }, { status: 401 })
    }
    
    const user = await authResponse.json()

    // Récupérer le fichier
    const formData = await request.formData()
    const file = formData.get('file') as File
    const verificationImageUrl = formData.get('verificationImageUrl') as string | null
    
    if (!file) {
      return NextResponse.json({ error: 'Aucun fichier fourni' }, { status: 400 })
    }

    // Vérifier le type de fichier
    const isImage = file.type.startsWith('image/')
    const isVideo = file.type.startsWith('video/')
    
    if (!isImage && !isVideo) {
      return NextResponse.json({ error: 'Type de fichier non supporté' }, { status: 400 })
    }

    // Convertir en base64 pour Sightengine
    const bytes = await file.arrayBuffer()
    const base64 = Buffer.from(bytes).toString('base64')
    const dataUri = `data:${file.type};base64,${base64}`

    // ============================================
    // ÉTAPE 1: MODÉRATION DU CONTENU
    // ============================================
    if (ENABLE_MODERATION && SIGHTENGINE_API_USER && SIGHTENGINE_API_SECRET) {
      console.log('🔍 Modération du contenu avant upload...')
      
      const moderationResult = await moderateContent(base64, file.type, isVideo)
      
      if (!moderationResult.isApproved) {
        console.warn('❌ Contenu rejeté:', moderationResult.flags)
        return NextResponse.json({
          error: 'Contenu rejeté par la modération',
          flags: moderationResult.flags,
          details: moderationResult.flags.map((f: ModerationFlag) => f.description).join(', ')
        }, { status: 422 })
      }
      
      console.log('✅ Contenu approuvé par la modération')

      // ============================================
      // ÉTAPE 2: VÉRIFICATION OWNERSHIP (si image de vérification fournie)
      // ============================================
      if (verificationImageUrl && isImage) {
        console.log('🔍 Vérification ownership...')
        
        const ownershipResult = await verifyOwnership(base64, verificationImageUrl)
        
        if (ownershipResult.faceDetected && !ownershipResult.isMatch) {
          console.warn('❌ Ownership non vérifié:', ownershipResult)
          return NextResponse.json({
            error: 'Le visage ne correspond pas à votre vérification',
            ownership: ownershipResult
          }, { status: 422 })
        }
        
        console.log('✅ Ownership vérifié')
      }
    }

    // ============================================
    // ÉTAPE 3: UPLOAD VERS UPLOADTHING
    // ============================================
    console.log('📤 Upload vers Uploadthing...')
    
    const utapi = new UTApi()
    
    // Créer un Blob à partir du fichier
    const blob = new Blob([bytes], { type: file.type })
    const uploadFile = new File([blob], file.name, { type: file.type })
    
    const uploadResponse = await utapi.uploadFiles([uploadFile])
    
    if (!uploadResponse[0]?.data) {
      console.error('Erreur upload:', uploadResponse[0]?.error)
      return NextResponse.json({ 
        error: 'Erreur lors de l\'upload',
        details: uploadResponse[0]?.error?.message 
      }, { status: 500 })
    }

    const uploadedFile = uploadResponse[0].data
    console.log('✅ Fichier uploadé:', uploadedFile.url)

    return NextResponse.json({
      success: true,
      file: {
        url: uploadedFile.url,
        key: uploadedFile.key,
        name: uploadedFile.name,
        size: uploadedFile.size,
        type: file.type
      },
      uploadedBy: user.id,
      moderated: ENABLE_MODERATION
    })

  } catch (error) {
    console.error('Erreur upload modéré:', error)
    return NextResponse.json({ 
      error: 'Erreur serveur',
      details: String(error)
    }, { status: 500 })
  }
}

/**
 * Modère le contenu avec Sightengine
 */
async function moderateContent(base64: string, mimeType: string, isVideo: boolean): Promise<{
  isApproved: boolean
  flags: ModerationFlag[]
}> {
  try {
    const formData = new URLSearchParams()
    formData.append('media', `data:${mimeType};base64,${base64}`)
    formData.append('models', 'nudity-2.0,violence,gore,weapon,offensive')
    formData.append('api_user', SIGHTENGINE_API_USER)
    formData.append('api_secret', SIGHTENGINE_API_SECRET)

    const endpoint = isVideo 
      ? 'https://api.sightengine.com/1.0/video/check-sync.json'
      : 'https://api.sightengine.com/1.0/check.json'

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData
    })

    if (!response.ok) {
      console.error('Sightengine API error:', response.status)
      // En cas d'erreur API, on laisse passer (fail-open)
      return { isApproved: true, flags: [] }
    }

    const data = await response.json()
    return processModerationResponse(data)
  } catch (error) {
    console.error('Moderation error:', error)
    return { isApproved: true, flags: [] }
  }
}

/**
 * Traite la réponse de Sightengine
 */
function processModerationResponse(data: any): { isApproved: boolean; flags: ModerationFlag[] } {
  const flags: ModerationFlag[] = []
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
  if (data.violence?.prob > MODERATION_THRESHOLDS.violence) {
    isApproved = false
    flags.push({
      type: 'violence',
      severity: data.violence.prob > 0.85 ? 'high' : 'medium',
      confidence: data.violence.prob,
      description: 'Contenu violent détecté'
    })
  }

  // Vérifier le gore
  if (data.gore?.prob > MODERATION_THRESHOLDS.gore) {
    isApproved = false
    flags.push({
      type: 'gore',
      severity: data.gore.prob > 0.7 ? 'high' : 'medium',
      confidence: data.gore.prob,
      description: 'Contenu gore/sanglant détecté'
    })
  }

  // Vérifier les armes
  if (data.weapon?.prob > MODERATION_THRESHOLDS.weapons) {
    isApproved = false
    flags.push({
      type: 'weapons',
      severity: 'medium',
      confidence: data.weapon.prob,
      description: 'Arme détectée'
    })
  }

  // Vérifier le contenu offensant
  if (data.offensive?.prob > MODERATION_THRESHOLDS.offensive) {
    isApproved = false
    flags.push({
      type: 'offensive',
      severity: 'medium',
      confidence: data.offensive.prob,
      description: 'Contenu offensant détecté'
    })
  }

  return { isApproved, flags }
}

/**
 * Vérifie l'ownership avec Sightengine Face Comparison
 */
async function verifyOwnership(base64: string, referenceUrl: string): Promise<{
  isMatch: boolean
  confidence: number
  faceDetected: boolean
}> {
  try {
    const formData = new URLSearchParams()
    formData.append('media', `data:image/jpeg;base64,${base64}`)
    formData.append('reference_url', referenceUrl)
    formData.append('api_user', SIGHTENGINE_API_USER)
    formData.append('api_secret', SIGHTENGINE_API_SECRET)

    const response = await fetch('https://api.sightengine.com/1.0/face/check.json', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData
    })

    if (!response.ok) {
      console.error('Face comparison API error:', response.status)
      return { isMatch: true, confidence: 0, faceDetected: false }
    }

    const data = await response.json()
    
    const faces = data.faces || []
    if (faces.length === 0) {
      return { isMatch: true, confidence: 0, faceDetected: false }
    }

    // Trouver la meilleure correspondance
    let bestMatch = 0
    for (const face of faces) {
      if (face.match?.similarity) {
        bestMatch = Math.max(bestMatch, face.match.similarity)
      }
    }

    return {
      isMatch: bestMatch >= 0.7,
      confidence: bestMatch,
      faceDetected: true
    }
  } catch (error) {
    console.error('Ownership verification error:', error)
    return { isMatch: true, confidence: 0, faceDetected: false }
  }
}
