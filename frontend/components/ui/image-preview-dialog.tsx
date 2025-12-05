'use client'

import React from 'react'
import { X } from 'lucide-react'

interface ImagePreviewDialogProps {
  isOpen: boolean
  imageUrl: string
  imageAlt?: string
  onClose: () => void
}

export function ImagePreviewDialog({
  isOpen,
  imageUrl,
  imageAlt = 'Image preview',
  onClose
}: ImagePreviewDialogProps) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[999999] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      {/* Blurred background image */}
      <div 
        className="absolute inset-0 bg-cover bg-center blur-3xl opacity-30"
        style={{ backgroundImage: `url(${imageUrl})` }}
      />
      
      <div 
        className="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden z-[9999999]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-2 bg-white/90 dark:bg-gray-800/90 rounded-full hover:bg-white dark:hover:bg-gray-700 transition-all z-[99999999]"
        >
          <X className="w-6 h-6 text-gray-900 dark:text-white" />
        </button>

        {/* Image Container with responsive size */}
        <div className="flex items-center justify-center p-8 w-screen h-screen max-w-4xl max-h-[90vh] sm:w-[800px] sm:h-[800px]">
          <img
            src={imageUrl}
            alt={imageAlt}
            className="w-full h-full object-contain"
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
