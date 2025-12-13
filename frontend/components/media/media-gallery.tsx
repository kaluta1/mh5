'use client'

import { Play, Image as ImageIcon } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { VideoEmbed } from '@/components/ui/video-embed'
import { detectVideoPlatform } from '@/lib/utils/video-platforms'

export interface MediaItem {
  id: string
  type: 'image' | 'video'
  url: string
  thumbnail?: string
}

export interface MediaGalleryProps {
  images: MediaItem[]
  videos: MediaItem[]
  onMediaSelect: (media: MediaItem) => void
}

export function MediaGallery({ images, videos, onMediaSelect }: MediaGalleryProps) {
  const { t } = useLanguage()

  return (
    <div className="space-y-6">
      {/* Images Grid */}
      {images.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-4">
            <ImageIcon className="w-5 h-5 text-myfav-primary" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              {t('contestant_detail.photos')} ({images.length})
            </h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-4">
            {images.map(media => (
              <div
                key={media.id}
                onClick={() => onMediaSelect(media)}
                className="aspect-square rounded-xl overflow-hidden cursor-pointer hover:scale-105 transition-transform shadow-md hover:shadow-xl"
              >
                <img
                  src={media.url}
                  alt="Photo"
                  className="w-full h-full object-cover"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Videos Grid */}
      {videos.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-4">
            <Play className="w-5 h-5 text-myfav-primary" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              {t('contestant_detail.videos')} ({videos.length})
            </h3>
          </div>
          <div className="grid grid-cols-2 gap-3 md:gap-4">
            {videos.map(media => (
              <div
                key={media.id}
                onClick={() => onMediaSelect(media)}
                className="aspect-square rounded-xl overflow-hidden cursor-pointer hover:scale-105 transition-transform shadow-md hover:shadow-xl relative group bg-gray-900"
              >
                {detectVideoPlatform(media.url) === 'direct' ? (
                  <>
                    {/* Video Thumbnail */}
                    <video
                      src={media.url}
                      className="w-full h-full object-cover"
                      onLoadedMetadata={(e) => {
                        const video = e.currentTarget
                        const canvas = document.createElement('canvas')
                        canvas.width = video.videoWidth
                        canvas.height = video.videoHeight
                        const ctx = canvas.getContext('2d')
                        if (ctx) {
                          ctx.drawImage(video, 0, 0)
                        }
                      }}
                    />
                    {/* Overlay with Play Button */}
                    <div className="absolute inset-0 bg-black/40 group-hover:bg-black/60 transition-all flex items-center justify-center">
                      <div className="flex items-center justify-center w-12 h-12 rounded-full bg-white/20 group-hover:bg-white/30 transition-all">
                        <Play className="w-6 h-6 text-white fill-white" />
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    {/* Video Embed Preview */}
                    <VideoEmbed
                      url={media.url}
                      className="w-full h-full pointer-events-none"
                      allowFullscreen={false}
                    />
                    {/* Overlay with Play Button */}
                    <div className="absolute inset-0 bg-black/20 group-hover:bg-black/40 transition-all flex items-center justify-center">
                      <div className="flex items-center justify-center w-12 h-12 rounded-full bg-white/20 group-hover:bg-white/30 transition-all">
                        <Play className="w-6 h-6 text-white fill-white" />
                      </div>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
