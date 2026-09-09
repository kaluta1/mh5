import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MediaImage } from './media-image'

describe('MediaImage', () => {
  it('does not render unsafe media URLs', () => {
    const { container } = render(<MediaImage src="javascript:alert(1)" alt="unsafe" />)
    expect(container.querySelector('img')).toBeNull()
  })

  it('renders normalized contest and contestant images', () => {
    render(<MediaImage src="/api/v1/media/file/5/contest.png" alt="contest" width={40} height={40} />)
    const image = screen.getByAltText('contest') as HTMLImageElement
    expect(image.src).toContain('/api/v1/media/file/5/contest.png')
  })

  it('switches to an intentional fallback after a load error', () => {
    const onError = vi.fn()
    render(
      <MediaImage
        src="https://cdn.example/missing.png"
        fallbackSrc="/images/fallback.png"
        alt="contestant"
        onError={onError}
      />,
    )
    const image = screen.getByAltText('contestant') as HTMLImageElement
    fireEvent.error(image)
    expect(image.src).toContain('/images/fallback.png')
    expect(onError).toHaveBeenCalledOnce()
  })

  it('removes a broken image when there is no fallback', () => {
    const { container } = render(<MediaImage src="https://cdn.example/missing.png" alt="missing" />)
    fireEvent.error(screen.getByAltText('missing'))
    expect(container.querySelector('img')).toBeNull()
  })
})
