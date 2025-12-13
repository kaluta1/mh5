'use client'

import { X, ChevronLeft, ChevronRight } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { MediaComments } from '@/components/comments'
import { VideoEmbed } from '@/components/ui/video-embed'
import { detectVideoPlatform } from '@/lib/utils/video-platforms'

export interface MediaItem {
  id: string
  type: 'image' | 'video'
  url: string
}

export interface MediaViewerModalProps {
  media: MediaItem | null
  allMedia?: MediaItem[]
  onClose: () => void
  onMediaChange?: (media: MediaItem) => void
  comments?: any[]
  onAddComment?: (text: string) => Promise<void>
}

export function MediaViewerModal({
  media,
  allMedia = [],
  onClose,
  onMediaChange,
  comments = [],
  onAddComment
}: MediaViewerModalProps) {
  const { t } = useLanguage()

  const currentIndex = media ? allMedia.findIndex(m => m.id === media.id) : -1
  
  const handlePrevious = () => {
    if (currentIndex > 0 && onMediaChange) {
      onMediaChange(allMedia[currentIndex - 1])
    }
  }

  const handleNext = () => {
    if (currentIndex < allMedia.length - 1 && onMediaChange) {
      onMediaChange(allMedia[currentIndex + 1])
    }
  }

  if (!media) return null

  return (
    <div
      className="fixed inset-0 bg-black/95 z-50 flex items-center justify-center p-2 md:p-4 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        className="max-w-7xl w-full h-full max-h-[95vh] relative flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Controls Bar */}
        <div className="absolute top-0 left-0 right-0 flex items-center justify-between px-4 md:px-6 py-3 md:py-4 z-30 bg-gradient-to-b from-black/80 via-black/60 to-transparent">
          <button
            onClick={onClose}
            className="text-white hover:bg-white/20 p-2.5 rounded-full transition-all backdrop-blur-sm border border-white/10 hover:border-white/20"
            title={t('contestant_detail.close') || 'Fermer'}
          >
            <X className="w-5 h-5 md:w-6 md:h-6" />
          </button>
          {allMedia.length > 1 && (
            <span className="text-white text-xs md:text-sm font-medium bg-black/60 backdrop-blur-sm px-3 py-1.5 rounded-full border border-white/10">
              {currentIndex + 1} / {allMedia.length}
            </span>
          )}
        </div>

        {/* Main Container */}
        <div className="flex-1 flex flex-col lg:flex-row bg-black/50 backdrop-blur-xl rounded-xl md:rounded-2xl overflow-hidden border border-white/10 shadow-2xl">
          {/* Media Container */}
          <div className="relative flex-1 flex items-center justify-center min-h-0 bg-black/30 overflow-hidden group">
            {media.type === 'image' ? (
              <img
                src={media.url}
                alt="Photo"
                className="max-w-full max-h-full w-auto h-auto object-contain"
              />
            ) : detectVideoPlatform(media.url) === 'direct' ? (
              <video
                src={media.url}
                controls
                className="max-w-full max-h-full w-auto h-auto object-contain"
              />
            ) : (
              <div className="w-full h-full max-w-4xl max-h-[80vh]">
                <VideoEmbed
                  url={media.url}
                  className="w-full h-full"
                  allowFullscreen={true}
                />
              </div>
            )}

            {/* Navigation Arrows */}
            {allMedia.length > 1 && (
              <>
                <button
                  onClick={handlePrevious}
                  disabled={currentIndex === 0}
                  className="absolute left-2 md:left-4 top-1/2 -translate-y-1/2 p-2.5 md:p-3 rounded-full bg-black/60 hover:bg-black/80 text-white transition-all disabled:opacity-30 disabled:cursor-not-allowed opacity-0 group-hover:opacity-100 backdrop-blur-md border border-white/20 hover:border-white/30"
                  aria-label="Précédent"
                >
                  <ChevronLeft className="w-5 h-5 md:w-6 md:h-6" />
                </button>

                <button
                  onClick={handleNext}
                  disabled={currentIndex === allMedia.length - 1}
                  className="absolute right-2 md:right-4 top-1/2 -translate-y-1/2 p-2.5 md:p-3 rounded-full bg-black/60 hover:bg-black/80 text-white transition-all disabled:opacity-30 disabled:cursor-not-allowed opacity-0 group-hover:opacity-100 backdrop-blur-md border border-white/20 hover:border-white/30"
                  aria-label="Suivant"
                >
                  <ChevronRight className="w-5 h-5 md:w-6 md:h-6" />
                </button>
              </>
            )}
          </div>

          {/* Comments Section */}
          {onAddComment && (
            <div className="lg:w-96 lg:max-w-md border-t lg:border-t-0 lg:border-l border-white/10 bg-black/40 backdrop-blur-xl flex flex-col max-h-[60vh] lg:max-h-full">
              <MediaComments
                mediaId={media.id}
                mediaType={media.type as 'photo' | 'video'}
                comments={comments}
                onAddComment={onAddComment}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
