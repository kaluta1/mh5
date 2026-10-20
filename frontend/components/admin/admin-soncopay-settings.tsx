'use client'

import { useCallback, useEffect, useState } from 'react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { financeErrorText } from '@/lib/finance-admin'
import {
  SONCOPAY_CONNECTION_TEST_URL,
  SONCOPAY_SETTINGS_URL,
  describeChanges,
  describeConnectionTest,
  describeCredential,
  draftFrom,
  draftProblems,
  settingsChanges,
  type CheckoutProvider,
  type SoncoPayConnectionTest,
  type SoncoPayCredentialStatus,
  type SoncoPayDraft,
  type SoncoPayEnvironment,
  type SoncoPaySettingsView,
} from '@/lib/soncopay-settings'
import { inputClass } from './admin-finance-ui'

const BADGE = {
  ok: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
  missing: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  warn: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
}

function CredentialBadge({ credential }: { credential?: SoncoPayCredentialStatus }) {
  if (!credential) return null
  const tone = credential.configured ? BADGE.ok : credential.saved ? BADGE.warn : BADGE.missing
  return (
    <span data-testid={`soncopay-credential-${credential.name}`}
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>
      {describeCredential(credential)}
    </span>
  )
}

function FieldError({ id, text }: { id: string; text?: string }) {
  if (!text) return null
  return <p id={id} className="text-xs text-red-600 dark:text-red-400">{text}</p>
}

type SecretField = 'testApiKey' | 'testWebhookSecret' | 'liveApiKey' | 'liveWebhookSecret'

/**
 * Finance & Payments > SoncoPay Configuration: customer payment collection.
 *
 * One form: on/off, Test/Live, the default customer checkout, and the API key
 * and webhook signing secret of each environment. Keys and secrets are write-only: the server stores them
 * encrypted and never sends a saved value back, so these fields always start
 * empty and a blank field keeps what is saved. Every change is authorized and
 * validated on the server (a Super Admin, plus the current password) and
 * audited without secret values. An administrator who may only view sees the
 * same form, read-only. NOWPayments checkout and payouts are not affected.
 * The connection test (a Super Admin) reads SoncoPay with the saved key; it
 * creates nothing and never shows the key.
 */
export default function AdminSoncoPaySettings() {
  const [view, setView] = useState<SoncoPaySettingsView | null>(null)
  const [draft, setDraft] = useState<SoncoPayDraft | null>(null)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<SoncoPayConnectionTest | null>(null)

  const show = (data: SoncoPaySettingsView) => {
    setView(data)
    setDraft(draftFrom(data))
  }

  const load = useCallback(async () => {
    const res = await api.get(SONCOPAY_SETTINGS_URL)
    if (res.status === 200) show(res.data)
    else setError(financeErrorText(res, 'The SoncoPay settings could not be loaded.'))
  }, [])

  useEffect(() => { void load() }, [load])

  const set = (patch: Partial<SoncoPayDraft>) => {
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
      <Card>
        <CardContent className="p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">SoncoPay settings</h2>
          {error ? <p className="text-sm text-red-600 dark:text-red-400 mt-2" role="alert">{error}</p>
            : <p className="text-sm text-gray-500 mt-2">Loading…</p>}
        </CardContent>
      </Card>
    )
  }

  const canChange = view.can_change
  const problems = draftProblems(view, draft)
  const changes = settingsChanges(view, draft)
  const credential = (name: string) => view.credentials.find((c) => c.name === name)
  const secretsDisabled = busy || !canChange || !view.encryption_key_configured
  const switchingToLive = draft.environment === 'live' && view.environment !== 'live'

  const save = async () => {
    if (!changes) return
    setBusy(true)
    setError('')
    setNotice('')
    const body = { ...changes, current_password: password, expected_version: view.version }
    // Nothing secret stays in the page once it has been sent.
    setPassword('')
    setDraft((d) => (d ? { ...d, testApiKey: '', testWebhookSecret: '', liveApiKey: '', liveWebhookSecret: '', confirmation: '' } : d))
    const res = await api.put(SONCOPAY_SETTINGS_URL, body)
    if (res.status === 200) {
      show(res.data)
      const what = describeChanges(res.data?.last_change?.changed)
      setNotice(what ? `Settings saved: ${what}.` : 'Settings saved.')
    } else {
      setError(financeErrorText(res, 'The settings could not be saved. Nothing was changed.'))
      if (res.status === 409) void load()
    }
    setBusy(false)
  }

  const testEnvironment: SoncoPayEnvironment = view.environment
  const runConnectionTest = async () => {
    setTesting(true)
    setTestResult(null)
    setError('')
    const res = await api.post(SONCOPAY_CONNECTION_TEST_URL, { environment: testEnvironment })
    if (res.status === 200) setTestResult(res.data)
    else setError(financeErrorText(res, 'The connection test could not be run.'))
    setTesting(false)
  }

  const secretInput = (field: SecretField, name: string, label: string, help: string) => {
    const status = credential(name)
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <label htmlFor={`soncopay-${field}`} className="block text-sm font-medium">{label}</label>
          <CredentialBadge credential={status} />
        </div>
        <input id={`soncopay-${field}`} type="password" autoComplete="off" spellCheck={false} className={inputClass}
          value={draft[field]} disabled={secretsDisabled} aria-invalid={!!problems[field]}
          aria-describedby={`soncopay-${field}-help`}
          placeholder={status?.configured ? 'Saved. Leave empty to keep it' : 'Paste the value'}
          onChange={(e) => set({ [field]: e.target.value } as Partial<SoncoPayDraft>)} />
        {problems[field] ? <FieldError id={`soncopay-${field}-help`} text={problems[field]} />
          : <p id={`soncopay-${field}-help`} className="text-xs text-gray-500">{help}</p>}
      </div>
    )
  }

  return (
    <Card>
      <CardContent className="p-6 space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">SoncoPay settings</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Customer payment collection. Managed here and stored in the database; keys and secrets are stored encrypted
            and never shown again: leave a field empty to keep what is saved. NOWPayments checkout and automatic
            commission payouts are not affected by these settings.
          </p>
        </div>

        <div role="status" data-testid="soncopay-checkout-state"
          className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-800 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-100">
          {view.default_provider_in_force === 'soncopay'
            ? `New member payments use SoncoPay (${view.environment === 'live' ? 'Live' : 'Test'}). Payments already started keep their own gateway.`
            : 'New member payments use NOWPayments. Payments already started keep their own gateway.'}
        </div>

        {!view.encryption_key_configured && (
          <p className="text-sm text-amber-700 dark:text-amber-300" role="status">
            PAYMENT_SETTINGS_ENCRYPTION_KEY is not configured on the server: keys and secrets cannot be saved until it is.
          </p>
        )}
        {!canChange && (
          <p className="text-sm text-amber-700 dark:text-amber-300" role="status">
            You can view these settings. Only a Super Admin can change them.
          </p>
        )}

        <div className="grid gap-5 sm:grid-cols-2 max-w-3xl" data-testid="soncopay-settings-form">
          <div className="sm:col-span-2 flex flex-wrap items-center gap-3">
            <Switch id="soncopay-enabled" checked={draft.enabled} disabled={busy || !canChange}
              onCheckedChange={(value) => set({ enabled: value })} aria-describedby="soncopay-enabled-help" />
            <label htmlFor="soncopay-enabled" className="text-sm font-medium">SoncoPay enabled</label>
            <span data-testid="soncopay-enabled-state"
              className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${view.enabled ? BADGE.ok : BADGE.missing}`}>
              {view.enabled ? 'Currently on' : 'Currently off'}
            </span>
            {problems.enabled ? <FieldError id="soncopay-enabled-help" text={problems.enabled} />
              : <p id="soncopay-enabled-help" className="w-full text-xs text-gray-500">
                  Needs the API key and webhook signing secret of the selected environment.
                </p>}
          </div>

          <div className="space-y-1">
            <label htmlFor="soncopay-environment" className="block text-sm font-medium">Environment</label>
            <select id="soncopay-environment" className={inputClass} value={draft.environment} disabled={busy || !canChange}
              onChange={(e) => set({ environment: e.target.value as SoncoPayEnvironment, confirmation: '' })}>
              <option value="test">Test</option>
              <option value="live">Live</option>
            </select>
            <p className="text-xs text-gray-500">In use now: {view.environment === 'live' ? 'Live' : 'Test'}.</p>
          </div>

          <div className="space-y-1">
            <label htmlFor="soncopay-default" className="block text-sm font-medium">Default customer checkout</label>
            <select id="soncopay-default" className={inputClass} value={draft.defaultProvider}
              disabled={busy || !canChange} aria-invalid={!!problems.defaultProvider}
              aria-describedby="soncopay-default-help"
              onChange={(e) => set({ defaultProvider: e.target.value as CheckoutProvider })}>
              {view.checkout_providers.map((p) => (
                <option key={p.provider} value={p.provider} disabled={!p.available}>
                  {p.label}{p.available ? '' : ' (not available)'}
                </option>
              ))}
            </select>
            {problems.defaultProvider ? <FieldError id="soncopay-default-help" text={problems.defaultProvider} />
              : <p id="soncopay-default-help" className="text-xs text-gray-500">
                  SoncoPay can be chosen while it is on and the selected environment&apos;s key and secret are saved.
                  In force now: {view.default_provider_in_force === 'soncopay' ? 'SoncoPay' : 'NOWPayments'}.
                </p>}
          </div>

          {switchingToLive && (
            <div className="sm:col-span-2 space-y-1">
              <label htmlFor="soncopay-confirmation" className="block text-sm font-medium">
                Type <code>{view.live_confirmation}</code> to switch to Live
              </label>
              <input id="soncopay-confirmation" className={inputClass} value={draft.confirmation} autoComplete="off"
                disabled={busy || !canChange} aria-invalid={!!problems.confirmation}
                aria-describedby="soncopay-confirmation-help" onChange={(e) => set({ confirmation: e.target.value })} />
              <FieldError id="soncopay-confirmation-help" text={problems.confirmation} />
            </div>
          )}

          <h3 className="sm:col-span-2 text-sm font-semibold text-gray-900 dark:text-white">Test credentials</h3>
          {secretInput('testApiKey', 'TEST_API_KEY', 'Test API key', 'From the SoncoPay dashboard, test mode.')}
          {secretInput('testWebhookSecret', 'TEST_WEBHOOK_SECRET', 'Test webhook signing secret',
            'The signing secret, not the webhook URL.')}

          <h3 className="sm:col-span-2 text-sm font-semibold text-gray-900 dark:text-white">Live credentials</h3>
          {secretInput('liveApiKey', 'LIVE_API_KEY', 'Live API key', 'From the SoncoPay dashboard, live mode.')}
          {secretInput('liveWebhookSecret', 'LIVE_WEBHOOK_SECRET', 'Live webhook signing secret',
            'The signing secret, not the webhook URL.')}

          <div className="sm:col-span-2 space-y-1">
            <label htmlFor="soncopay-webhook-url" className="block text-sm font-medium">
              Webhook URL (register it in the SoncoPay dashboard)
            </label>
            <div className="flex gap-2">
              <input id="soncopay-webhook-url" readOnly className={inputClass} value={view.webhook_url || ''}
                placeholder="Not available: BACKEND_PUBLIC_URL is not set" onFocus={(e) => e.target.select()} />
              <Button type="button" variant="outline" onClick={() => void copyWebhookUrl()} disabled={!view.webhook_url}>
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
          </div>

          <div className="sm:col-span-2 flex flex-wrap items-center gap-3">
            <Button type="button" variant="outline" data-testid="soncopay-connection-test"
              disabled={!view.connection_test.available || !canChange || testing || busy}
              onClick={() => void runConnectionTest()}>
              {testing ? 'Testing…' : `Connection Test (${testEnvironment === 'live' ? 'Live' : 'Test'})`}
            </Button>
            {!view.connection_test.available && view.connection_test.reason && (
              <span className="text-xs text-gray-500">{view.connection_test.reason}</span>
            )}
            {testResult && (
              <span data-testid="soncopay-connection-result" role="status"
                className={`text-xs ${testResult.ok ? 'text-green-700 dark:text-green-300' : 'text-red-600 dark:text-red-400'}`}>
                {describeConnectionTest(testResult)}
              </span>
            )}
            <span className="w-full text-xs text-gray-500">
              Reads SoncoPay with the saved key of the environment in use. Nothing is created or charged.
            </span>
          </div>

          {canChange && (
            <>
              <div className="space-y-1">
                <label htmlFor="soncopay-password" className="block text-sm font-medium">Your current password</label>
                <input id="soncopay-password" type="password" autoComplete="current-password" className={inputClass}
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
