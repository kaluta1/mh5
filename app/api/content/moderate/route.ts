import { NextRequest, NextResponse } from 'next/server'
import { moderateImage, moderateVideo, type ModerationResult } from '@/lib/services/content-moderation-service'

/**
 * API pour modérer un contenu (image ou vidéo)
 * 
 * POST /api/content/moderate
 * Body: { contentUrl: string, contentType: 'image' | 'video' }
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { contentUrl, contentType } = body

    if (!contentUrl) {
      return NextResponse.json(
        { error: 'contentUrl est requis' },
        { status: 400 }
      )
    }

    const type = contentType || 'image'
    
    let result: ModerationResult
    
    if (type === 'video') {
      result = await moderateVideo(contentUrl)
    } else {
      result = await moderateImage(contentUrl)
    }

    return NextResponse.json({
      success: true,
      moderation: {
        isApproved: result.isApproved,
        confidence: result.confidence,
        flags: result.flags.map(f => ({
          type: f.type,
          severity: f.severity,
          confidence: f.confidence,
          description: f.description
        })),
        details: result.details
      }
    })
  } catch (error) {
    console.error('Content moderation error:', error)
    return NextResponse.json(
      { error: 'Erreur lors de la modération', details: String(error) },
      { status: 500 }
    )
  }
}
