'use client'

import { useEffect, useState } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { CheckCircle, XCircle, Loader2, Mail } from 'lucide-react'
import { Button } from '@/components/ui/button'
import Link from 'next/link'

export default function VerifyEmailPage() {
  const { t } = useLanguage()
  const searchParams = useSearchParams()
  const router = useRouter()
  const token = searchParams.get('token')
  
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [email, setEmail] = useState('')

  useEffect(() => {
    const verifyEmail = async () => {
      if (!token) {
        setStatus('error')
        setMessage(t('auth.verify_email.no_token') || 'No verification token provided')
        return
      }

      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/verify-email?token=${encodeURIComponent(token)}`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
          }
        )

        const data = await response.json()

        if (response.ok) {
          setStatus('success')
          setMessage(t('auth.verify_email.success') || 'Your email has been verified successfully!')
          setEmail(data.email || '')
        } else {
          setStatus('error')
          if (response.status === 400) {
            setMessage(t('auth.verify_email.invalid_token') || 'Invalid or expired verification link')
          } else if (response.status === 404) {
            setMessage(t('auth.verify_email.user_not_found') || 'User not found')
          } else {
            setMessage(data.detail || t('auth.verify_email.error') || 'An error occurred during verification')
          }
        }
      } catch (error) {
        console.error('Email verification error:', error)
        setStatus('error')
        setMessage(t('auth.verify_email.error') || 'An error occurred during verification')
      }
    }

    verifyEmail()
  }, [token, t])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 via-white to-gray-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900 px-4">
      <div className="w-full max-w-md">
        <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-8 text-center animate-in fade-in zoom-in duration-500">
          {/* Logo/Icon */}
          <div className="mb-6">
            {status === 'loading' && (
              <div className="w-20 h-20 mx-auto bg-blue-100 dark:bg-blue-900/30 rounded-full flex items-center justify-center">
                <Loader2 className="w-10 h-10 text-blue-600 dark:text-blue-400 animate-spin" />
              </div>
            )}
            {status === 'success' && (
              <div className="w-20 h-20 mx-auto bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center animate-in zoom-in duration-300">
                <CheckCircle className="w-10 h-10 text-green-600 dark:text-green-400" />
              </div>
            )}
            {status === 'error' && (
              <div className="w-20 h-20 mx-auto bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center animate-in zoom-in duration-300">
                <XCircle className="w-10 h-10 text-red-600 dark:text-red-400" />
              </div>
            )}
          </div>

          {/* Title */}
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
            {status === 'loading' && (t('auth.verify_email.verifying') || 'Verifying your email...')}
            {status === 'success' && (t('auth.verify_email.verified_title') || 'Email Verified!')}
            {status === 'error' && (t('auth.verify_email.failed_title') || 'Verification Failed')}
          </h1>

          {/* Message */}
          <p className="text-gray-600 dark:text-gray-400 mb-6">
            {status === 'loading' && (t('auth.verify_email.please_wait') || 'Please wait while we verify your email address...')}
            {(status === 'success' || status === 'error') && message}
          </p>

          {/* Email display for success */}
          {status === 'success' && email && (
            <div className="mb-6 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg flex items-center justify-center gap-2">
              <Mail className="w-4 h-4 text-gray-500 dark:text-gray-400" />
              <span className="text-sm text-gray-700 dark:text-gray-300">{email}</span>
            </div>
          )}

          {/* Actions */}
          {status === 'success' && (
            <div className="space-y-3">
              <Link href="/login" className="block">
                <Button className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl py-3">
                  {t('auth.verify_email.go_to_login') || 'Go to Login'}
                </Button>
              </Link>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t('auth.verify_email.can_login_now') || 'You can now log in to your account'}
              </p>
            </div>
          )}

          {status === 'error' && (
            <div className="space-y-3">
              <Link href="/register" className="block">
                <Button className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl py-3">
                  {t('auth.verify_email.register_again') || 'Register Again'}
                </Button>
              </Link>
              <Link href="/" className="block">
                <Button variant="outline" className="w-full rounded-xl py-3">
                  {t('auth.verify_email.go_home') || 'Go to Homepage'}
                </Button>
              </Link>
            </div>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-sm text-gray-500 dark:text-gray-400 mt-6">
          {t('auth.verify_email.need_help') || 'Need help?'}{' '}
          <Link href="/contact" className="text-purple-600 dark:text-purple-400 hover:underline">
            {t('auth.verify_email.contact_support') || 'Contact Support'}
          </Link>
        </p>
      </div>
    </div>
  )
}
