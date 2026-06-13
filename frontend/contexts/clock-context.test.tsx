import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { ClockProvider, useClock } from './clock-context'

function wrapper({ children }: { children: React.ReactNode }) {
  return <ClockProvider>{children}</ClockProvider>
}

describe('ClockProvider', () => {
  it('provides a Date value that updates over time', async () => {
    const { result } = renderHook(() => useClock(), { wrapper })
    const first = result.current.getTime()
    expect(first).toBeGreaterThan(0)

    await waitFor(() => expect(result.current.getTime()).toBeGreaterThan(first), {
      timeout: 2000,
      interval: 100,
    })
  })
})
