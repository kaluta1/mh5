'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Mail, ShieldAlert } from 'lucide-react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'

/**
 * Admin > Email Settings (EMAIL-1): Overview, Provider, Events, Delivery Logs.
 *
 * The backend authorizes everything. Reading needs an administrator; every
 * change, the API key and the test email need the explicit
 * manage_email_settings permission (`can_manage`). No secret is ever received
 * from the API: the key field is write-only and is cleared after saving.
 */
const BASE = '/api/v1/admin/email-settings'

type Warning = { code: string; level: 'critical' | 'warning'; message: string }

type Overview = {
  status: 'active' | 'critical_only' | 'unavailable' | 'stopped'
  email_enabled: boolean
  emergency_stop: boolean
  provider: { resend_enabled: boolean; configured: boolean; key_source: string }
  critical_events: { key: string; label: string; enabled: boolean }[]
  critical_email_active: boolean
  stats: { queued: number; processing: number; sent_24h: number; failed_24h: number; suppressed_24h: number }
  warnings: Warning[]
  can_manage: boolean
  emergency_stop_phrase: string
}

type Provider = {
  resend_enabled: boolean
  configured: boolean
  key_source: string
  environment_key_configured: boolean
  override_configured: boolean
  override_readable: boolean
  override_last4: string | null
  override_updated_at: string | null
  encryption_key_configured: boolean
  from_name: string | null
  from_address: string | null
  effective_from_name: string
  effective_from_address: string
  reply_to: string | null
  support_address: string | null
  effective_support_address: string
  admin_alert_recipients: string[]
  allowed_from_domains: string[]
}

type EmailEvent = {
  key: string
  label: string
  category: string
  classification: string
  recipient: string
  critical: boolean
  default_enabled: boolean
  enabled: boolean
  phase: string
  trigger_implemented: boolean
  disable_warning: string | null
}

type Delivery = {
  id: number
  created_at: string | null
  event_key: string
  event_label: string
  category: string
  recipient: string
  provider: string | null
  status: string
  attempts: number
  provider_message_id: string | null
  failure_category: string | null
}

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'provider', label: 'Provider' },
  { id: 'events', label: 'Events' },
  { id: 'logs', label: 'Delivery Logs' },
] as const
type TabId = (typeof TABS)[number]['id']

const STATUS_LABEL: Record<Overview['status'], string> = {
  active: 'Active',
  critical_only: 'Security email only',
  unavailable: 'Not sending (provider)',
  stopped: 'Emergency stop',
}

const KEY_SOURCE_LABEL: Record<string, string> = {
  admin_override: 'Admin override',
  environment: 'Environment',
  none: 'None',
}

const DELIVERY_STATUSES = ['QUEUED', 'PROCESSING', 'SENT', 'DELIVERED', 'DELAYED', 'FAILED', 'BOUNCED', 'COMPLAINED', 'SUPPRESSED']

const inputClass = 'w-full px-3 py-2 border rounded-md bg-white dark:bg-gray-800 text-sm border-gray-300 dark:border-gray-700'

function errorText(res: { status: number; data?: any }, fallback: string): string {
  if (res.status === 403) return 'You do not have the manage_email_settings permission.'
  const detail = res.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return fallback
}

function StatusPill({ tone, children }: { tone: 'green' | 'amber' | 'red' | 'gray'; children: React.ReactNode }) {
  const tones = {
    green: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
    amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
    red: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    gray: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  }
  return <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${tones[tone]}`}>{children}</span>
}

export default function AdminEmailSettings() {
  const [tab, setTab] = useState<TabId>('overview')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [provider, setProvider] = useState<Provider | null>(null)
  const [events, setEvents] = useState<EmailEvent[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const loadOverview = useCallback(async () => {
    const res = await api.get(`${BASE}/overview`)
    if (res.status === 200) setOverview(res.data)
    else setError(res.status === 403 ? 'You are not allowed to view email settings.' : 'Could not load email settings.')
  }, [])
  const loadProvider = useCallback(async () => {
    const res = await api.get(`${BASE}/provider`)
    if (res.status === 200) setProvider(res.data)
  }, [])
  const loadEvents = useCallback(async () => {
    const res = await api.get(`${BASE}/events`)
    if (res.status === 200) setEvents(res.data.events)
  }, [])

  useEffect(() => { loadOverview(); loadProvider(); loadEvents() }, [loadOverview, loadProvider, loadEvents])

  const canManage = !!overview?.can_manage

  /** Run one change, then refresh. Returns true when the server accepted it. */
  const change = async (request: () => Promise<{ status: number; data?: any }>, ok: string, failure: string) => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const res = await request()
      if (res.status === 200) {
        setNotice(ok)
        await Promise.all([loadOverview(), loadProvider(), loadEvents()])
        return true
      }
      setError(errorText(res, failure))
      return false
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div role="tablist" className="flex flex-wrap gap-2 border-b border-gray-200 dark:border-gray-700">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === t.id
              ? 'border-myhigh5-primary text-myhigh5-primary'
              : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {notice && <p role="status" className="text-sm text-green-700 dark:text-green-400">{notice}</p>}
      {overview && !canManage && (
        <p className="text-sm text-gray-600 dark:text-gray-400">
          You can view email settings. Changing them needs the <code>manage_email_settings</code> permission.
        </p>
      )}

      {tab === 'overview' && overview && (
        <OverviewTab overview={overview} busy={busy} canManage={canManage}
          onMaster={(enabled) => change(() => api.put(`${BASE}/master`, { enabled }),
            enabled ? 'Email system enabled.' : 'Email system disabled. Security email is still sent.',
            'The email system switch could not be changed.')}
          onEmergency={(active, confirmation) => change(
            () => api.put(`${BASE}/emergency-stop`, { active, confirmation }),
            active ? 'Emergency stop is active. No email is being sent.' : 'Emergency stop lifted.',
            'The emergency stop could not be changed.')} />
      )}
      {tab === 'provider' && provider && (
        <ProviderTab provider={provider} busy={busy} canManage={canManage} change={change}
          setError={setError} setNotice={setNotice} />
      )}
      {tab === 'events' && (
        <EventsTab events={events} busy={busy} canManage={canManage}
          onToggle={(event, enabled, confirmCritical) => change(
            () => api.put(`${BASE}/events/${encodeURIComponent(event.key)}`, { enabled, confirm_critical: confirmCritical }),
            `${event.label}: ${enabled ? 'enabled' : 'disabled'}.`, 'The event switch could not be changed.')} />
      )}
      {tab === 'logs' && <LogsTab events={events} />}
    </div>
  )
}

function OverviewTab({ overview, busy, canManage, onMaster, onEmergency }: {
  overview: Overview
  busy: boolean
  canManage: boolean
  onMaster: (enabled: boolean) => void
  onEmergency: (active: boolean, confirmation: string) => Promise<boolean>
}) {
  const [confirming, setConfirming] = useState(false)
  const [phrase, setPhrase] = useState('')
  const tone = overview.status === 'active' ? 'green' : overview.status === 'critical_only' ? 'amber' : 'red'

  return (
    <div className="space-y-4">
      {overview.warnings.map((w) => (
        <div key={w.code} role="alert"
          className={`flex items-start gap-2 p-3 rounded-lg border text-sm ${w.level === 'critical'
            ? 'border-red-300 bg-red-50 text-red-800 dark:bg-red-900/20 dark:text-red-300'
            : 'border-amber-300 bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-300'}`}>
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{w.message}</span>
        </div>
      ))}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardContent className="p-4 space-y-3">
            <h2 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2"><Mail className="w-4 h-4" /> Email system</h2>
            <p className="text-sm">Status: <StatusPill tone={tone}>{STATUS_LABEL[overview.status]}</StatusPill></p>
            <p className="text-sm">
              Resend provider:{' '}
              <StatusPill tone={overview.provider.configured && overview.provider.resend_enabled ? 'green' : 'red'}>
                {!overview.provider.resend_enabled ? 'Disabled' : overview.provider.configured ? 'Configured' : 'Not configured'}
              </StatusPill>
              <span className="text-gray-500"> · key source: {KEY_SOURCE_LABEL[overview.provider.key_source] ?? overview.provider.key_source}</span>
            </p>
            <p className="text-sm">
              Security-critical email:{' '}
              <StatusPill tone={overview.critical_email_active ? 'green' : 'red'}>
                {overview.critical_email_active ? 'Active' : 'Not fully active'}
              </StatusPill>
            </p>
            <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
              <div>
                <p className="text-sm font-medium">Email System</p>
                <p className="text-xs text-gray-500">Normal application email. Security email is not affected by this switch.</p>
              </div>
              <Switch aria-label="Email System" checked={overview.email_enabled} disabled={!canManage || busy}
                onCheckedChange={(v) => onMaster(v)} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 space-y-2">
            <h2 className="font-semibold text-gray-900 dark:text-white">Delivery health</h2>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-gray-500">Queued</dt><dd data-testid="stat-queued">{overview.stats.queued}</dd>
              <dt className="text-gray-500">Sending now</dt><dd>{overview.stats.processing}</dd>
              <dt className="text-gray-500">Sent (24h)</dt><dd>{overview.stats.sent_24h}</dd>
              <dt className="text-gray-500">Failed (24h)</dt><dd data-testid="stat-failed">{overview.stats.failed_24h}</dd>
              <dt className="text-gray-500">Suppressed (24h)</dt><dd>{overview.stats.suppressed_24h}</dd>
            </dl>
          </CardContent>
        </Card>
      </div>

      <Card className="border-red-300 dark:border-red-800">
        <CardContent className="p-4 space-y-3">
          <h2 className="font-semibold text-red-700 dark:text-red-400 flex items-center gap-2">
            <ShieldAlert className="w-4 h-4" /> Emergency Stop All Email
          </h2>
          <p className="text-sm text-gray-700 dark:text-gray-300">
            Stops every email, including email verification, password reset, password-changed notices and guardian
            consent email. Members will not be able to reset a password or verify an address while it is active.
            Email stopped this way is not sent later.
          </p>
          {overview.emergency_stop ? (
            <Button variant="outline" disabled={!canManage || busy} onClick={() => onEmergency(false, '')}>
              Lift emergency stop
            </Button>
          ) : !confirming ? (
            <Button variant="destructive" disabled={!canManage || busy} onClick={() => setConfirming(true)}>
              Stop all email…
            </Button>
          ) : (
            <div className="space-y-2">
              <label className="block text-sm" htmlFor="emergency-phrase">
                Type <strong>{overview.emergency_stop_phrase}</strong> to confirm
              </label>
              <input id="emergency-phrase" className={inputClass} value={phrase} autoComplete="off"
                onChange={(e) => setPhrase(e.target.value)} />
              <div className="flex gap-2">
                <Button variant="destructive" disabled={busy || phrase.trim() !== overview.emergency_stop_phrase}
                  onClick={async () => { if (await onEmergency(true, phrase.trim())) { setConfirming(false); setPhrase('') } }}>
                  Confirm emergency stop
                </Button>
                <Button variant="outline" onClick={() => { setConfirming(false); setPhrase('') }}>Cancel</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function ProviderTab({ provider, busy, canManage, change, setError, setNotice }: {
  provider: Provider
  busy: boolean
  canManage: boolean
  change: (request: () => Promise<{ status: number; data?: any }>, ok: string, failure: string) => Promise<boolean>
  setError: (value: string) => void
  setNotice: (value: string) => void
}) {
  const [form, setForm] = useState({
    from_name: provider.from_name ?? '',
    from_address: provider.from_address ?? '',
    reply_to: provider.reply_to ?? '',
    support_address: provider.support_address ?? '',
    admin_alert_recipients: provider.admin_alert_recipients.join(', '),
  })
  // Write-only: never pre-filled, cleared as soon as it has been sent.
  const [apiKey, setApiKey] = useState('')
  const [testRecipient, setTestRecipient] = useState('')
  const [testing, setTesting] = useState(false)
  const field = (name: keyof typeof form) => ({
    value: form[name],
    disabled: !canManage || busy,
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [name]: e.target.value }),
  })

  const save = () => change(() => api.put(`${BASE}/provider`, {
    from_name: form.from_name,
    from_address: form.from_address,
    reply_to: form.reply_to,
    support_address: form.support_address,
    admin_alert_recipients: form.admin_alert_recipients.split(/[,\s]+/).map((v) => v.trim()).filter(Boolean),
  }), 'Sender settings saved.', 'The sender settings could not be saved.')

  const saveKey = async () => {
    const value = apiKey
    setApiKey('')
    await change(() => api.put(`${BASE}/provider/api-key`, { api_key: value }),
      'API key override saved. It is stored encrypted and cannot be shown again.', 'The API key could not be saved.')
  }

  const sendTest = async () => {
    setTesting(true)
    setError('')
    setNotice('')
    try {
      const res = await api.post(`${BASE}/test`, { recipient: testRecipient.trim() })
      if (res.status === 200 && res.data.success) setNotice(`Test email sent to ${res.data.recipient}.`)
      else if (res.status === 200) setError(`The test email was not sent (${res.data.failure_category ?? res.data.status}).`)
      else setError(errorText(res, 'The test email could not be sent.'))
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card>
        <CardContent className="p-4 space-y-3">
          <h2 className="font-semibold text-gray-900 dark:text-white">Resend</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Resend provider</p>
              <p className="text-xs text-gray-500">When disabled, no email can be sent at all.</p>
            </div>
            <Switch aria-label="Resend provider" checked={provider.resend_enabled} disabled={!canManage || busy}
              onCheckedChange={(v) => change(() => api.put(`${BASE}/provider`, { resend_enabled: v }),
                v ? 'Resend provider enabled.' : 'Resend provider disabled.', 'The provider switch could not be changed.')} />
          </div>
          <dl className="grid grid-cols-2 gap-2 text-sm pt-2 border-t border-gray-200 dark:border-gray-700">
            <dt className="text-gray-500">API key</dt>
            <dd>{provider.configured ? 'Configured' : 'Not configured'}</dd>
            <dt className="text-gray-500">Source</dt>
            <dd data-testid="key-source">{KEY_SOURCE_LABEL[provider.key_source] ?? provider.key_source}</dd>
            <dt className="text-gray-500">Environment key configured</dt>
            <dd>{provider.environment_key_configured ? 'Yes' : 'No'}</dd>
            <dt className="text-gray-500">Admin override</dt>
            <dd>{provider.override_configured ? `Configured (ends in ${provider.override_last4 ?? '????'})` : 'None'}</dd>
            {provider.override_updated_at && (<>
              <dt className="text-gray-500">Override last updated</dt>
              <dd>{new Date(provider.override_updated_at).toLocaleString()}</dd>
            </>)}
          </dl>

          <div className="space-y-2 pt-2 border-t border-gray-200 dark:border-gray-700">
            <label className="block text-sm font-medium" htmlFor="resend-api-key">
              {provider.override_configured ? 'Replace API key override' : 'Set API key override'}
            </label>
            <input id="resend-api-key" type="password" autoComplete="new-password" className={inputClass}
              placeholder="Paste a Resend API key" value={apiKey} disabled={!canManage || busy || !provider.encryption_key_configured}
              onChange={(e) => setApiKey(e.target.value)} />
            <p className="text-xs text-gray-500">
              Stored encrypted. It is never shown again, here or anywhere else.
              {!provider.encryption_key_configured && ' The server has no EMAIL_SETTINGS_ENCRYPTION_KEY, so an override cannot be stored.'}
            </p>
            <div className="flex gap-2">
              <Button disabled={!canManage || busy || apiKey.trim().length < 10} onClick={saveKey}>Save API key</Button>
              {provider.override_configured && (
                <Button variant="outline" disabled={!canManage || busy}
                  onClick={() => change(() => api.delete(`${BASE}/provider/api-key`),
                    'API key override removed. The environment key is used when one is configured.',
                    'The API key override could not be removed.')}>
                  Remove override
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4 space-y-3">
          <h2 className="font-semibold text-gray-900 dark:text-white">Sender</h2>
          <div>
            <label className="block text-sm font-medium" htmlFor="from-name">From name</label>
            <input id="from-name" className={inputClass} placeholder={provider.effective_from_name} {...field('from_name')} />
          </div>
          <div>
            <label className="block text-sm font-medium" htmlFor="from-address">From address</label>
            <input id="from-address" type="email" className={inputClass} placeholder={provider.effective_from_address} {...field('from_address')} />
            {provider.allowed_from_domains.length > 0 && (
              <p className="text-xs text-gray-500">Verified sending domain: {provider.allowed_from_domains.join(', ')}</p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium" htmlFor="reply-to">Reply-to address</label>
            <input id="reply-to" type="email" className={inputClass} placeholder="Optional" {...field('reply_to')} />
          </div>
          <div>
            <label className="block text-sm font-medium" htmlFor="support-address">Support address</label>
            <input id="support-address" type="email" className={inputClass} placeholder={provider.effective_support_address} {...field('support_address')} />
          </div>
          <div>
            <label className="block text-sm font-medium" htmlFor="alert-recipients">Admin alert recipients</label>
            <input id="alert-recipients" className={inputClass} placeholder="Comma separated. Empty: every active admin."
              {...field('admin_alert_recipients')} />
          </div>
          <Button disabled={!canManage || busy} onClick={save}>Save sender settings</Button>
        </CardContent>
      </Card>

      <Card className="lg:col-span-2">
        <CardContent className="p-4 space-y-2">
          <h2 className="font-semibold text-gray-900 dark:text-white">Send test email</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Sends one clearly labelled test message to one address. It is recorded in the delivery log.
          </p>
          <div className="flex flex-wrap gap-2">
            <input aria-label="Test recipient" type="email" className={`${inputClass} max-w-sm`} placeholder="name@example.com"
              value={testRecipient} disabled={!canManage || testing} onChange={(e) => setTestRecipient(e.target.value)} />
            <Button disabled={!canManage || testing || !/^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$/.test(testRecipient.trim())}
              onClick={sendTest}>
              Send test email
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function EventsTab({ events, busy, canManage, onToggle }: {
  events: EmailEvent[]
  busy: boolean
  canManage: boolean
  onToggle: (event: EmailEvent, enabled: boolean, confirmCritical: boolean) => Promise<boolean>
}) {
  const [pending, setPending] = useState<EmailEvent | null>(null)
  const groups = useMemo(() => {
    const map = new Map<string, EmailEvent[]>()
    events.forEach((e) => map.set(e.category, [...(map.get(e.category) ?? []), e]))
    return Array.from(map.entries())
  }, [events])

  const toggle = (event: EmailEvent, enabled: boolean) => {
    if (event.critical && !enabled) setPending(event)
    else onToggle(event, enabled, false)
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600 dark:text-gray-400">
        {events.length} email events. A switch decides whether an email may be sent. Events marked
        “Trigger not implemented” are not emitted by the application yet, whatever their switch says.
      </p>

      {pending && (
        <div role="alertdialog" aria-label="Disable security email"
          className="p-4 rounded-lg border border-red-300 bg-red-50 dark:bg-red-900/20 space-y-2">
          <p className="font-semibold text-red-800 dark:text-red-300">Disable “{pending.label}”?</p>
          <p className="text-sm text-red-800 dark:text-red-300">{pending.disable_warning}</p>
          <div className="flex gap-2">
            <Button variant="destructive" disabled={busy}
              onClick={async () => { await onToggle(pending, false, true); setPending(null) }}>
              Disable this security email
            </Button>
            <Button variant="outline" onClick={() => setPending(null)}>Cancel</Button>
          </div>
        </div>
      )}

      {groups.map(([category, items]) => (
        <Card key={category}>
          <CardContent className="p-4">
            <h2 className="font-semibold text-gray-900 dark:text-white mb-2">{category}</h2>
            <ul className="divide-y divide-gray-200 dark:divide-gray-700">
              {items.map((event) => (
                <li key={event.key} className="flex items-center gap-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {event.label}{' '}
                      {event.critical && <StatusPill tone="red">Critical</StatusPill>}{' '}
                      {!event.trigger_implemented && <StatusPill tone="gray">Trigger not implemented</StatusPill>}
                    </p>
                    <p className="text-xs text-gray-500">
                      <code>{event.key}</code> · {event.classification} · to {event.recipient}
                    </p>
                  </div>
                  <Switch aria-label={event.label} checked={event.enabled} disabled={!canManage || busy}
                    onCheckedChange={(v) => toggle(event, v)} />
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function LogsTab({ events }: { events: EmailEvent[] }) {
  const [filters, setFilters] = useState({ event: '', category: '', status: '', provider: '', date_from: '', date_to: '' })
  const [page, setPage] = useState(1)
  const [data, setData] = useState<{ total: number; limit: number; items: Delivery[] }>({ total: 0, limit: 25, items: [] })
  const [failed, setFailed] = useState(false)
  const categories = useMemo(() => Array.from(new Set(events.map((e) => e.category))), [events])

  const load = useCallback(async () => {
    const params: Record<string, string | number> = { page, limit: 25 }
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v })
    const res = await api.get(`${BASE}/deliveries`, { params })
    if (res.status === 200) { setData(res.data); setFailed(false) } else setFailed(true)
  }, [filters, page])

  useEffect(() => { load() }, [load])

  const set = (name: keyof typeof filters) => (e: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>) => {
    setPage(1)
    setFilters({ ...filters, [name]: e.target.value })
  }
  const selectClass = 'px-2 py-1 border rounded bg-white dark:bg-gray-800 text-sm border-gray-300 dark:border-gray-700'
  const pages = Math.max(1, Math.ceil(data.total / data.limit))

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex flex-wrap gap-2 items-center">
          <select aria-label="Event" className={selectClass} value={filters.event} onChange={set('event')}>
            <option value="">All events</option>
            {events.map((e) => <option key={e.key} value={e.key}>{e.label}</option>)}
            <option value="SYSTEM.TEST_EMAIL">Test email</option>
          </select>
          <select aria-label="Category" className={selectClass} value={filters.category} onChange={set('category')}>
            <option value="">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select aria-label="Status" className={selectClass} value={filters.status} onChange={set('status')}>
            <option value="">All statuses</option>
            {DELIVERY_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select aria-label="Provider" className={selectClass} value={filters.provider} onChange={set('provider')}>
            <option value="">All providers</option>
            <option value="resend">resend</option>
          </select>
          <input aria-label="From date" type="date" className={selectClass} value={filters.date_from} onChange={set('date_from')} />
          <input aria-label="To date" type="date" className={selectClass} value={filters.date_to} onChange={set('date_to')} />
        </div>
        {failed && <p role="alert" className="text-sm text-red-600">Could not load the delivery log.</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-200 dark:border-gray-700">
                <th className="py-2 pr-3">Time</th><th className="pr-3">Event</th><th className="pr-3">Recipient</th>
                <th className="pr-3">Provider</th><th className="pr-3">Status</th><th className="pr-3">Attempts</th>
                <th className="pr-3">Provider message ID</th><th>Failure</th>
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 && (
                <tr><td colSpan={8} className="py-4 text-gray-500">No deliveries match.</td></tr>
              )}
              {data.items.map((d) => (
                <tr key={d.id} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-2 pr-3 whitespace-nowrap">{d.created_at ? new Date(`${d.created_at}Z`).toLocaleString() : '-'}</td>
                  <td className="pr-3">{d.event_label}</td>
                  <td className="pr-3">{d.recipient}</td>
                  <td className="pr-3">{d.provider ?? '-'}</td>
                  <td className="pr-3">
                    <StatusPill tone={d.status === 'SENT' || d.status === 'DELIVERED' ? 'green'
                      : d.status === 'FAILED' || d.status === 'BOUNCED' || d.status === 'COMPLAINED' ? 'red'
                        : d.status === 'SUPPRESSED' ? 'gray' : 'amber'}>{d.status}</StatusPill>
                  </td>
                  <td className="pr-3">{d.attempts}</td>
                  <td className="pr-3 font-mono text-xs">{d.provider_message_id ?? '-'}</td>
                  <td>{d.failure_category ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Button variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <span>Page {page} of {pages} · {data.total} deliveries</span>
          <Button variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      </CardContent>
    </Card>
  )
}
