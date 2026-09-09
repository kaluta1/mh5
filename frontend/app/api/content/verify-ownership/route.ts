import { NextRequest, NextResponse } from 'next/server'
import { verifyOwnership, moderateImage } from '@/lib/services/content-moderation-service'
import { hasValidBackendBearer } from '@/lib/server-auth'

/**
 * API pour vérifier que l'auteur du contenu uploadé est le même que le selfie de vérification
 * 
 * POST /api/content/verify-ownership
 * Body: { verificationImageUrl: string, uploadedImageUrl: string }
 */
export async function POST(request: NextRequest) {
  try {
    if (!(await hasValidBackendBearer(request))) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }
    const body = await request.json()
    const { verificationImageUrl, uploadedImageUrl } = body

    if (!verificationImageUrl || !uploadedImageUrl) {
      return NextResponse.json(
        { error: 'verificationImageUrl et uploadedImageUrl sont requis' },
        { status: 400 }
      )
    }

    // Vérifier l'ownership (comparaison de visages)
    const ownershipResult = await verifyOwnership(verificationImageUrl, uploadedImageUrl)

    return NextResponse.json({
      success: true,
      ownership: {
        isMatch: ownershipResult.isMatch,
        confidence: ownershipResult.confidence,
        faceDetected: ownershipResult.faceDetected,
        details: ownershipResult.matchDetails
      }
    })
  } catch (error) {
    console.error('Ownership verification error:', error)
    return NextResponse.json(
      { error: 'Erreur lors de la vérification' },
      { status: 500 }
    )
  }
}
