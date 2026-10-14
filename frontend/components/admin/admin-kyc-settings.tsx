'use client'

import { useCallback, useEffect, useState } from 'react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { financeErrorText } from '@/lib/finance-admin'
import {
  KYC_ADMIN_SETTINGS_URL,
  describeCredential,
  looksLikeUrl,
  settingsChanges,
  type KycAdminSettingsView,
} from '@/lib/kyc-settings'
import { inputClass } from './admin-finance-ui'

/**
 * Admin > KYC: Kaluta KYC settings.
 *
 * The API key and the webhook secret are write-only: the server stores them
 * encrypted and never sends a saved value back, so these fields always start
 * empty and a blank field keeps what is saved. Every change is authorized on
 * the server (manage_kyc_settings + current password) and audited without the
 * values.
 */
export default function AdminKycSettings() {
  const [view, setView] = useState<KycAdminSettingsView | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [webhookSecret, setWebhookSecret] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState(false)

  const show = (data: KycAdminSettingsView) => {
    setView(data)
    setEnabled(data.enabled)
  }

  const load = useCallback(async () => {
    const res = await api.get(KYC_ADMIN_SETTINGS_URL)
    if (res.status === 200) show(res.data)
    else setError('The Kaluta KYC settings could not be loaded.')
  }, [])

  useEffect(() => { void load() }, [load])

  const changes = view ? settingsChanges(view, { enabled, apiKey, webhookSecret }) : null
  const urlPasted = looksLikeUrl(apiKey) || looksLikeUrl(webhookSecret)
  const canChange = !!view?.can_change

  const copyWebhookUrl = async () => {
    if (!view?.webhook_url) return
    try {
      await navigator.clipboard.writeText(view.webhook_url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setError('The webhook URL could not be copied. Select it and copy it by hand.')
    }
  }

  const save = async () => {
    if (!view || !changes) return
    setBusy(true)
    setError('')
    setNotice('')
    const body = { ...changes, current_password: password, expected_version: view.version }
    // Nothing secret stays in the page once it has been sent.
    setPassword('')
    setApiKey('')
    setWebhookSecret('')
    const res = await api.put(KYC_ADMIN_SETTINGS_URL, body)
    if (res.status === 200) {
      show(res.data)
      setNotice('Saved.')
    } else {
      setError(financeErrorText(res, 'The settings could not be saved.'))
      setEnabled(view.enabled)
      if (res.status === 409) void load()
    }
    setBusy(false)
  }

  return (
    <Card className="mb-8">
      <CardContent className="p-6 space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Kaluta KYC settings</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            The API key and webhook secret are stored encrypted and are never shown again. Leave a field empty to keep
            what is saved.
          </p>
        </div>

        {view && (
          <dl className="grid gap-2 text-sm sm:grid-cols-2 max-w-3xl" data-testid="kyc-settings-state">
            <div>
              <dt className="text-gray-500">Kaluta KYC</dt>
              <dd className="font-medium">
                {view.enabled ? 'On' : 'Off'}{' '}
                <span className="text-gray-500 font-normal">
                  ({view.enabled_source === 'admin_panel' ? 'set in the Admin Panel' : 'from the server environment'})
                </span>
              </dd>
            </div>
            {view.credentials.map((c) => (
              <div key={c.name} data-testid={`kyc-credential-${c.name}`}>
                <dt className="text-gray-500">{c.label}</dt>
                <dd className="font-medium">{describeCredential(c)}</dd>
              </div>
            ))}
            <div>
              <dt className="text-gray-500">Sessions per attempt</dt>
              <dd className="font-medium">{view.sessions_per_attempt}</dd>
            </div>
          </dl>
        )}

        {view && (
          <div className="space-y-1 max-w-3xl">
            <label htmlFor="kyc-webhook-url" className="block text-sm font-medium">Webhook URL (register it in the Kaluta dashboard)</label>
            <div className="flex gap-2">
              <input id="kyc-webhook-url" readOnly className={inputClass} value={view.webhook_url || ''}
                placeholder="Not available: BACKEND_PUBLIC_URL is not set" onFocus={(e) => e.target.select()} />
              <Button type="button" variant="outline" onClick={() => void copyWebhookUrl()} disabled={!view.webhook_url}>
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
          </div>
        )}

        {view && !view.encryption_key_configured && (
          <p className="text-sm text-amber-700 dark:text-amber-300" role="status">
            PAYMENT_SETTINGS_ENCRYPTION_KEY is not configured on the server: a key or secret cannot be saved here.
          </p>
        )}

        {view && !canChange && (
          <p className="text-sm text-amber-700 dark:text-amber-300" role="status">
            You can view these settings. Changing them needs the {view.permission} permission.
          </p>
        )}

        {view && canChange && (
          <div className="grid gap-4 sm:grid-cols-2 max-w-3xl">
            <div className="sm:col-span-2 flex items-center gap-2">
              <input id="kyc-enabled" type="checkbox" checked={enabled} disabled={busy}
                onChange={(e) => setEnabled(e.target.checked)} />
              <label htmlFor="kyc-enabled" className="text-sm font-medium">Kaluta KYC enabled</label>
              {enabled && !view.enabled && !view.ready_to_enable && !(apiKey.trim() || webhookSecret.trim()) && (
                <span className="text-xs text-amber-700 dark:text-amber-300">Save the API key and webhook secret first.</span>
              )}
            </div>
            <div className="space-y-1">
              <label htmlFor="kyc-api-key" className="block text-sm font-medium">New Kaluta API key</label>
              <input id="kyc-api-key" type="password" autoComplete="off" spellCheck={false} className={inputClass}
                value={apiKey} disabled={busy || !view.encryption_key_configured} placeholder="Leave empty to keep"
                onChange={(e) => setApiKey(e.target.value)} />
            </div>
            <div className="space-y-1">
              <label htmlFor="kyc-webhook-secret" className="block text-sm font-medium">New Kaluta webhook secret</label>
              <input id="kyc-webhook-secret" type="password" autoComplete="off" spellCheck={false} className={inputClass}
                value={webhookSecret} disabled={busy || !view.encryption_key_configured} placeholder="Leave empty to keep"
                onChange={(e) => setWebhookSecret(e.target.value)} />
              <p className="text-xs text-gray-500">The signing secret from Kaluta, not the webhook URL.</p>
            </div>
            {urlPasted && (
              <p className="sm:col-span-2 text-sm text-red-600 dark:text-red-400" role="alert">
                That looks like a URL. Paste the key or the signing secret, not the webhook URL.
              </p>
            )}
            <div className="space-y-1">
              <label htmlFor="kyc-settings-password" className="block text-sm font-medium">Your current password</label>
              <input id="kyc-settings-password" type="password" autoComplete="current-password" className={inputClass}
                value={password} disabled={busy} onChange={(e) => setPassword(e.target.value)} />
              <p className="text-xs text-gray-500">Required to confirm the change.</p>
            </div>
            <div className="sm:col-span-2">
              <Button onClick={() => void save()} disabled={busy || !changes || !password || urlPasted}>
                {busy ? 'Saving…' : 'Save KYC settings'}
              </Button>
            </div>
          </div>
        )}

        {notice && <p className="text-sm text-green-700 dark:text-green-300" role="status">{notice}</p>}
        {error && <p className="text-sm text-red-600 dark:text-red-400" role="alert">{error}</p>}
      </CardContent>
    </Card>
  )
}
