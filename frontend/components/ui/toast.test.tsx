import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { ToastProvider, useToast } from './toast'

function TestComponent() {
  const { addToast } = useToast()
  return (
    <button onClick={() => addToast('Hello from test', 'success')}>
      Show Toast
    </button>
  )
}

describe('ToastProvider', () => {
  it('renders children', () => {
    render(
      <ToastProvider>
        <div data-testid="child">Child</div>
      </ToastProvider>
    )
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('shows a toast when addToast is called', async () => {
    render(
      <ToastProvider>
        <TestComponent />
      </ToastProvider>
    )

    act(() => {
      screen.getByRole('button', { name: /show toast/i }).click()
    })

    await waitFor(() => {
      expect(screen.getByText('Hello from test')).toBeInTheDocument()
    })
  })
})
