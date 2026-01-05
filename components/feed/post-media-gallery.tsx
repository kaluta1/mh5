'use client'

import { useState } from 'react'
import Image from 'next/image'
import { PostMedia } from '@/services/social-service'
import { ImagePreviewDialog } from '@/components/ui/image-preview-dialog'
import { VideoPreviewDialog } from '@/components/ui/video-preview-dialog'
import { cn } from '@/lib/utils'

interface PostMediaGalleryProps {
  media: PostMedia[]
}

export function PostMediaGallery({ media }: PostMediaGalleryProps) {
  const [selectedImage, setSelectedImage] = useState<string | null>(null)
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null)

  if (media.length === 0) return null

  if (media.length === 1) {
    const item = media[0]
    if (item.media_type === 'image') {
      return (
        <>
          <div 
            className="relative w-full rounded-lg overflow-hidden cursor-pointer"
            onClick={() => setSelectedImage(item.url)}
          >
            <Image
              src={item.url}
              alt="Post media"
              width={800}
              height={600}
              className="w-full h-auto object-cover"
            />
          </div>
          {selectedImage && (
            <ImagePreviewDialog
              isOpen={!!selectedImage}
              imageUrl={selectedImage}
              onClose={() => setSelectedImage(null)}
            />
          )}
        </>
      )
    } else {
      return (
        <>
          <div 
            className="relative w-full rounded-lg overflow-hidden cursor-pointer"
            onClick={() => setSelectedVideo(item.url)}
          >
            <video
              src={item.url}
              poster={item.thumbnail_url}
              controls
              className="w-full h-auto"
            />
          </div>
          {selectedVideo && (
            <VideoPreviewDialog
              isOpen={!!selectedVideo}
              videoUrl={selectedVideo}
              onClose={() => setSelectedVideo(null)}
            />
          )}
        </>
      )
    }
  }

  if (media.length === 2) {
    return (
      <div className="grid grid-cols-2 gap-2">
        {media.map((item, index) => (
          <MediaItem
            key={item.id}
            item={item}
            onImageClick={setSelectedImage}
            onVideoClick={setSelectedVideo}
          />
        ))}
        {selectedImage && (
          <ImagePreviewDialog
            isOpen={!!selectedImage}
            imageUrl={selectedImage}
            onClose={() => setSelectedImage(null)}
          />
        )}
        {selectedVideo && (
          <VideoPreviewDialog
            isOpen={!!selectedVideo}
            videoUrl={selectedVideo}
            onClose={() => setSelectedVideo(null)}
          />
        )}
      </div>
    )
  }

  if (media.length === 3) {
    return (
      <div className="grid grid-cols-2 gap-2">
        <div className="row-span-2">
          <MediaItem
            item={media[0]}
            onImageClick={setSelectedImage}
            onVideoClick={setSelectedVideo}
          />
        </div>
        <div>
          <MediaItem
            item={media[1]}
            onImageClick={setSelectedImage}
            onVideoClick={setSelectedVideo}
          />
        </div>
        <div>
          <MediaItem
            item={media[2]}
            onImageClick={setSelectedImage}
            onVideoClick={setSelectedVideo}
          />
        </div>
        {selectedImage && (
          <ImagePreviewDialog
            isOpen={!!selectedImage}
            imageUrl={selectedImage}
            onClose={() => setSelectedImage(null)}
          />
        )}
        {selectedVideo && (
          <VideoPreviewDialog
            isOpen={!!selectedVideo}
            videoUrl={selectedVideo}
            onClose={() => setSelectedVideo(null)}
          />
        )}
      </div>
    )
  }

  // 4+ images
  return (
    <div className="grid grid-cols-2 gap-2">
      {media.slice(0, 4).map((item, index) => (
        <div key={item.id} className="relative">
          <MediaItem
            item={item}
            onImageClick={setSelectedImage}
            onVideoClick={setSelectedVideo}
          />
          {index === 3 && media.length > 4 && (
            <div className="absolute inset-0 bg-black/50 flex items-center justify-center rounded-lg cursor-pointer">
              <span className="text-white text-2xl font-bold">
                +{media.length - 4}
              </span>
            </div>
          )}
        </div>
      ))}
      {selectedImage && (
        <ImagePreviewDialog
          isOpen={!!selectedImage}
          imageUrl={selectedImage}
          onClose={() => setSelectedImage(null)}
        />
      )}
      {selectedVideo && (
        <VideoPreviewDialog
          isOpen={!!selectedVideo}
          videoUrl={selectedVideo}
          onClose={() => setSelectedVideo(null)}
        />
      )}
    </div>
  )
}

function MediaItem({ 
  item, 
  onImageClick, 
  onVideoClick 
}: { 
  item: PostMedia
  onImageClick: (url: string) => void
  onVideoClick: (url: string) => void
}) {
  if (item.media_type === 'image') {
    return (
      <div 
        className="relative w-full aspect-square rounded-lg overflow-hidden cursor-pointer"
        onClick={() => onImageClick(item.url)}
      >
        <Image
          src={item.url}
          alt="Post media"
          fill
          className="object-cover"
        />
      </div>
    )
  } else {
    return (
      <div 
        className="relative w-full aspect-square rounded-lg overflow-hidden cursor-pointer"
        onClick={() => onVideoClick(item.url)}
      >
        <video
          src={item.url}
          poster={item.thumbnail_url}
          className="w-full h-full object-cover"
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-16 h-16 rounded-full bg-black/50 flex items-center justify-center">
            <svg className="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 20 20">
              <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
            </svg>
          </div>
        </div>
      </div>
    )
  }
}

