'use client'

import React from 'react'
import { X } from 'lucide-react'

interface VideoPreviewDialogProps {
  isOpen: boolean
  videoUrl: string
  videoTitle?: string
  onClose: () => void
}

export function VideoPreviewDialog({
  isOpen,
  videoUrl,
  videoTitle = 'Video preview',
  onClose
}: VideoPreviewDialogProps) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[999999] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div 
        className="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl max-w-4xl max-h-[90vh] overflow-hidden z-[9999999]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 bg-white/90 dark:bg-gray-800/90 rounded-full hover:bg-white dark:hover:bg-gray-700 transition-all z-[99999999]"
        >
          <X className="w-6 h-6 text-gray-900 dark:text-white" />
        </button>

        {/* Video Container */}
        <div className="relative w-screen h-screen max-w-4xl max-h-[90vh] sm:w-[800px] sm:h-[600px] bg-black flex items-center justify-center">
          <video
            src={videoUrl}
            title={videoTitle}
            controls
            className="w-full h-full object-contain"
            autoPlay
          />
        </div>

        {/* Click to close hint */}
        <div className="absolute bottom-4 left-0 right-0 text-center text-sm text-gray-500 dark:text-gray-400">
          Cliquez pour fermer
        </div>
      </div>
    </div>
  )
}
