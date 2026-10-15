'use client'

import { useCallback, useEffect, useState } from 'react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { financeErrorText } from '@/lib/finance-admin'
import {
  KYC_ADMIN_SETTINGS_URL,
  describeChanges,
  describeCredential,
  draftFrom,
  draftProblems,
  settingsChanges,
  type KycAdminSettingsView,
  type KycCredentialStatus,
  type KycSettingsDraft,
} from '@/lib/kyc-settings'
import { inputClass } from './admin-finance-ui'

const BADGE = {
  ok: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  missing: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  warn: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
}

function CredentialBadge({ credential }: { credential: KycCredentialStatus }) {
  const tone = credential.configured ? BADGE.ok : credential.saved ? BADGE.warn : BADGE.missing
  return (
    <span data-testid={`kyc-credential-${credential.name}`}
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>
      {describeCredential(credential)}
    </span>
  )
}

function FieldError({ id, text }: { id: string; text?: string }) {
  if (!text) return null
  return <p id={id} className="text-xs text-red-600 dark:text-red-400">{text}</p>
}

/**
 * Admin > KYC: Kaluta KYC settings, managed here only (stored in the
 * database; the server environment is not used).
 *
 * One form: on/off, API key, webhook secret, the member KYC fee and the
 * sessions per attempt. The API key and the webhook secret are write-only: the
 * server stores them encrypted and never sends a saved value back, so these
 * fields always start empty and a blank field keeps what is saved. Every
 * change is authorized and validated on the server (manage_kyc_settings or a
 * Super Admin, plus the current password) and audited without secret values.
 * An administrator without the permission sees the same form, read-only.
 */
export default function AdminKycSettings() {
  const [view, setView] = useState<KycAdminSettingsView | null>(null)
  const [draft, setDraft] = useState<KycSettingsDraft | null>(null)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState(false)

  const show = (data: KycAdminSettingsView) => {
    setView(data)
    setDraft(draftFrom(data))
  }

  const load = useCallback(async () => {
    const res = await api.get(KYC_ADMIN_SETTINGS_URL)
    if (res.status === 200) show(res.data)
    else setError(financeErrorText(res, 'The KYC settings could not be loaded.'))
  }, [])

  useEffect(() => { void load() }, [load])

  const set = (patch: Partial<KycSettingsDraft>) => {
    setDraft((d) => (d ? { ...d, ...patch } : d))
    setNotice('')
  }

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

  if (!view || !draft) {
    return (
      <Card className="mb-8">
        <CardContent className="p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Kaluta KYC settings</h2>
          {error ? <p className="text-sm text-red-600 dark:text-red-400 mt-2" role="alert">{error}</p>
            : <p className="text-sm text-gray-500 mt-2">Loading…</p>}
        </CardContent>
      </Card>
    )
  }

  const canChange = view.can_change
  const problems = draftProblems(view, draft)
  const changes = settingsChanges(view, draft)
  const [apiKeyStatus, secretStatus] = [
    view.credentials.find((c) => c.name === 'API_KEY'),
    view.credentials.find((c) => c.name === 'WEBHOOK_SECRET'),
  ]
  const secretsDisabled = busy || !canChange || !view.encryption_key_configured
  const switchingOnWithoutSecrets = draft.enabled && !view.enabled && !view.ready_to_enable
    && !((apiKeyStatus?.configured || draft.apiKey.trim()) && (secretStatus?.configured || draft.webhookSecret.trim()))

  const save = async () => {
    if (!changes) return
    setBusy(true)
    setError('')
    setNotice('')
    const body = {
      ...changes,
      current_password: password,
      expected_version: view.version,
      ...(changes.member_fee !== undefined ? { expected_fee: view.member_fee.amount } : {}),
    }
    // Nothing secret stays in the page once it has been sent.
    setPassword('')
    setDraft((d) => (d ? { ...d, apiKey: '', webhookSecret: '' } : d))
    const res = await api.put(KYC_ADMIN_SETTINGS_URL, body)
    if (res.status === 200) {
      show(res.data)
      const what = describeChanges(res.data?.last_change?.changed)
      setNotice(what ? `Settings saved: ${what}.` : 'Settings saved.')
    } else {
      setError(financeErrorText(res, 'The settings could not be saved. Nothing was changed.'))
      // The secrets were cleared; every other field keeps what the administrator typed.
      if (res.status === 409) void load()
    }
    setBusy(false)
  }

  return (
    <Card className="mb-8">
      <CardContent className="p-6 space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Kaluta KYC settings</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Managed here and stored in the database. The API key and webhook secret are stored encrypted and are never
            shown again: leave a field empty to keep what is saved.
          </p>
        </div>

        {!view.encryption_key_configured && (
          <p className="text-sm text-amber-700 dark:text-amber-300" role="status">
            PAYMENT_SETTINGS_ENCRYPTION_KEY is not configured on the server: the API key and webhook secret cannot be
            saved until it is.
          </p>
        )}
        {!canChange && (
          <p className="text-sm text-amber-700 dark:text-amber-300" role="status">
            You can view these settings. Changing them needs the {view.permission} permission or a Super Admin.
          </p>
        )}

        <div className="grid gap-5 sm:grid-cols-2 max-w-3xl" data-testid="kyc-settings-form">
          <div className="sm:col-span-2 flex flex-wrap items-center gap-3">
            <Switch id="kyc-enabled" checked={draft.enabled} disabled={busy || !canChange}
              onCheckedChange={(value) => set({ enabled: value })} aria-describedby="kyc-enabled-help" />
            <label htmlFor="kyc-enabled" className="text-sm font-medium">Kaluta KYC enabled</label>
            <span data-testid="kyc-enabled-state"
              className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${view.enabled ? BADGE.ok : BADGE.missing}`}>
              {view.enabled ? 'Currently on' : 'Currently off'}
            </span>
            <p id="kyc-enabled-help" className="w-full text-xs text-gray-500">
              {switchingOnWithoutSecrets
                ? 'Enter the API key and the webhook secret too: Kaluta KYC cannot be switched on without them.'
                : 'When off, members cannot start a verification and Kaluta webhooks are refused.'}
            </p>
          </div>

          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <label htmlFor="kyc-api-key" className="block text-sm font-medium">Kaluta API key</label>
              {apiKeyStatus && <CredentialBadge credential={apiKeyStatus} />}
            </div>
            <input id="kyc-api-key" type="password" autoComplete="off" spellCheck={false} className={inputClass}
              value={draft.apiKey} disabled={secretsDisabled} aria-invalid={!!problems.apiKey}
              aria-describedby="kyc-api-key-error"
              placeholder={apiKeyStatus?.configured ? 'Saved. Leave empty to keep it' : 'Paste the API key'}
              onChange={(e) => set({ apiKey: e.target.value })} />
            <FieldError id="kyc-api-key-error" text={problems.apiKey} />
          </div>

          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <label htmlFor="kyc-webhook-secret" className="block text-sm font-medium">Kaluta webhook secret</label>
              {secretStatus && <CredentialBadge credential={secretStatus} />}
            </div>
            <input id="kyc-webhook-secret" type="password" autoComplete="off" spellCheck={false} className={inputClass}
              value={draft.webhookSecret} disabled={secretsDisabled} aria-invalid={!!problems.webhookSecret}
              aria-describedby="kyc-webhook-secret-error"
              placeholder={secretStatus?.configured ? 'Saved. Leave empty to keep it' : 'Paste the signing secret'}
              onChange={(e) => set({ webhookSecret: e.target.value })} />
            <FieldError id="kyc-webhook-secret-error" text={problems.webhookSecret} />
            {!problems.webhookSecret && <p className="text-xs text-gray-500">The signing secret from Kaluta, not the webhook URL.</p>}
          </div>

          <div className="space-y-1">
            <label htmlFor="kyc-fee" className="block text-sm font-medium">KYC verification fee (USD)</label>
            <input id="kyc-fee" type="number" inputMode="decimal" min={0} max={Number(view.member_fee.max_amount)} step="0.01"
              className={inputClass} value={draft.fee} aria-invalid={!!problems.fee} aria-describedby="kyc-fee-help"
              disabled={busy || !canChange || !view.member_fee.product_configured}
              onChange={(e) => set({ fee: e.target.value })} />
            {problems.fee ? <FieldError id="kyc-fee-help" text={problems.fee} /> : (
              <p id="kyc-fee-help" className="text-xs text-gray-500">
                {!view.member_fee.product_configured
                  ? 'The KYC product is not set up on this server, so the fee cannot be changed.'
                  : 'For new verification attempts. 0 makes KYC free. Payments that already exist keep their amount.'}
              </p>
            )}
          </div>

          <div className="space-y-1">
            <label htmlFor="kyc-sessions" className="block text-sm font-medium">Sessions per attempt</label>
            <input id="kyc-sessions" type="number" inputMode="numeric" min={view.sessions_per_attempt_min}
              max={view.sessions_per_attempt_max} step={1} className={inputClass} value={draft.sessions}
              aria-invalid={!!problems.sessions} aria-describedby="kyc-sessions-help" disabled={busy || !canChange}
              onChange={(e) => set({ sessions: e.target.value })} />
            {problems.sessions ? <FieldError id="kyc-sessions-help" text={problems.sessions} /> : (
              <p id="kyc-sessions-help" className="text-xs text-gray-500">
                Verification links a member can open for one paid attempt (default {view.sessions_per_attempt_default}).
              </p>
            )}
          </div>

          <div className="sm:col-span-2 space-y-1">
            <label htmlFor="kyc-webhook-url" className="block text-sm font-medium">Webhook URL (register it in the Kaluta dashboard)</label>
            <div className="flex gap-2">
              <input id="kyc-webhook-url" readOnly className={inputClass} value={view.webhook_url || ''}
                placeholder="Not available: BACKEND_PUBLIC_URL is not set" onFocus={(e) => e.target.select()} />
              <Button type="button" variant="outline" onClick={() => void copyWebhookUrl()} disabled={!view.webhook_url}>
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
          </div>

          {canChange && (
            <>
              <div className="space-y-1">
                <label htmlFor="kyc-settings-password" className="block text-sm font-medium">Your current password</label>
                <input id="kyc-settings-password" type="password" autoComplete="current-password" className={inputClass}
                  value={password} disabled={busy} onChange={(e) => setPassword(e.target.value)} />
                <p className="text-xs text-gray-500">Required to confirm the change.</p>
              </div>
              <div className="sm:col-span-2 flex flex-wrap items-center gap-3">
                <Button onClick={() => void save()} disabled={busy || !changes || !password}>
                  {busy ? 'Saving…' : 'Save Settings'}
                </Button>
                {!changes && !Object.keys(problems).length && (
                  <span className="text-xs text-gray-500">No changes to save.</span>
                )}
              </div>
            </>
          )}
        </div>

        {notice && <p className="text-sm text-green-700 dark:text-green-300" role="status">{notice}</p>}
        {error && <p className="text-sm text-red-600 dark:text-red-400" role="alert">{error}</p>}
      </CardContent>
    </Card>
  )
}
