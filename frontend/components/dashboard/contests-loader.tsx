'use client'

import React from 'react'

interface ContestsLoaderProps {
  isLoading: boolean
  hasMore: boolean
  observerTarget: React.RefObject<HTMLDivElement>
}

export function ContestsLoader({ isLoading, hasMore, observerTarget }: ContestsLoaderProps) {
  if (!hasMore) {
    return null
  }

  return (
    <div ref={observerTarget} className="py-8 flex justify-center">
      {isLoading && (
        <div className="flex gap-2">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="w-3 h-3 bg-myhigh5-primary rounded-full animate-bounce"
              style={{
                animationDelay: `${i * 0.2}s`,
                animationDuration: '1.4s'
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}
