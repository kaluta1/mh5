'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { readFragmentToken } from '@/lib/guardian-consent'

/**
 * Finish a guardian-approved registration. The single-use token comes from
 * the URL fragment. The password is chosen here (it was never stored while
 * the request was pending). The server decides whether the account can be
 * created.
 */
export default function CompleteRegistrationPage() {
  const [token, setToken] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setToken(readFragmentToken(typeof window !== 'undefined' ? window.location.hash : ''))
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    try {
      const res = await api.post('/api/v1/auth/register/complete', { token, password })
      if (res.status === 201) {
        setDone(true)
      } else if (Array.isArray(res.data?.detail)) {
        setError(res.data.detail.join(' '))
      } else {
        setError(typeof res.data?.detail === 'string' ? res.data.detail : 'This link is invalid or has expired.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-4">
      <div className="w-full max-w-md bg-white dark:bg-gray-800 rounded-2xl shadow p-6 space-y-4">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Finish creating your account</h1>
        {!token && <p className="text-gray-700 dark:text-gray-200">This link is invalid or has expired.</p>}
        {token && done && (
          <p className="text-gray-700 dark:text-gray-200">
            Your account has been created. <Link className="underline" href="/login">Sign in</Link>
          </p>
        )}
        {token && !done && (
          <form onSubmit={submit} className="space-y-3">
            <Input type="password" placeholder="Choose a password" value={password}
                   onChange={(e) => setPassword(e.target.value)} required />
            <Input type="password" placeholder="Confirm password" value={confirm}
                   onChange={(e) => setConfirm(e.target.value)} required />
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button type="submit" disabled={busy} className="w-full">Create account</Button>
          </form>
        )}
      </div>
    </main>
  )
}
