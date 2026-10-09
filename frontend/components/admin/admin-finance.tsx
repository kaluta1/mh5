'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { AlertTriangle, ShieldAlert } from 'lucide-react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import {
  FINANCE_BASE,
  FINANCE_SECTIONS,
  changedValues,
  checkLabel,
  credentialPayload,
  dateTime,
  financeErrorText,
  humanize,
  readinessTone,
  webhookStatusLabel,
  type FinanceOverview,
  type FinanceSection,
  type FinanceSettings,
  type ProviderView,
  type SettingField,
  type WebhookHealth,
} from '@/lib/finance-admin'
import { CashoutTransactions, ReconciliationAndAudit } from './admin-finance-cashouts'
import { Row, StatusPill, TonePill, inputClass } from './admin-finance-ui'

/**
 * Admin > Finance & Payments.
 *
 * The backend authorizes and validates everything. Reading needs an
 * administrator; a configuration change needs the manage_payment_settings
 * permission and the administrator's current password, sent with the change.
 * No secret is ever received from the API: credential fields are write-only,
 * a blank field keeps the stored value, and they are cleared after saving.
 */
type Change = (request: () => Promise<{ status: number; data?: any }>, ok: string, failure: string) => Promise<boolean>

function PasswordField({ id, value, onChange, disabled }: {
  id: string; value: string; onChange: (value: string) => void; disabled?: boolean
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">Your current password</label>
      <input id={id} type="password" autoComplete="current-password" className={inputClass} value={value}
        disabled={disabled} onChange={(e) => onChange(e.target.value)} />
      <p className="text-xs text-gray-500">Required to confirm every change in Finance &amp; Payments.</p>
    </div>
  )
}

export default function AdminFinance({ section }: { section: FinanceSection }) {
  const [overview, setOverview] = useState<FinanceOverview | null>(null)
  const [provider, setProvider] = useState<ProviderView | null>(null)
  const [settings, setSettings] = useState<FinanceSettings | null>(null)
  const [webhook, setWebhook] = useState<WebhookHealth | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const [o, p, s, w] = await Promise.all([
      api.get(`${FINANCE_BASE}/overview`), api.get(`${FINANCE_BASE}/provider`),
      api.get(`${FINANCE_BASE}/settings`), api.get(`${FINANCE_BASE}/webhook`),
    ])
    if (o.status === 200) setOverview(o.data)
    else setError(o.status === 403 ? 'You are not allowed to view Finance & Payments.' : 'Finance & Payments could not be loaded.')
    if (p.status === 200) setProvider(p.data)
    if (s.status === 200) setSettings(s.data)
    if (w.status === 200) setWebhook(w.data)
  }, [])

  useEffect(() => { void load() }, [load])

  const canManage = !!overview?.permissions.can_manage
  const canProcess = !!overview?.permissions.can_process

  /** Run one change, then refresh. Returns true when the server accepted it. */
  const change: Change = async (request, ok, failure) => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const res = await request()
      if (res.status === 200) {
        setNotice(ok)
        await load()
        return true
      }
      setError(financeErrorText(res, failure))
      return false
    } finally {
      setBusy(false)
    }
  }

  const group = (name: SettingField['group']) => settings?.fields.filter((f) => f.group === name) ?? []

  return (
    <div className="space-y-4">
      <nav aria-label="Finance & Payments sections" className="flex flex-wrap gap-2 border-b border-gray-200 dark:border-gray-700">
        {FINANCE_SECTIONS.map((s) => (
          <Link key={s.slug} href={`/dashboard/admin/finance/${s.slug}`} aria-current={section === s.slug ? 'page' : undefined}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px ${section === s.slug
              ? 'border-myhigh5-primary text-myhigh5-primary'
              : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'}`}>
            {s.label}
          </Link>
        ))}
      </nav>

      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {notice && <p role="status" className="text-sm text-green-700 dark:text-green-400">{notice}</p>}
      {overview && !canManage && (
        <p className="text-sm text-gray-600 dark:text-gray-400">
          You can view Finance &amp; Payments. Changing the configuration needs the <code>manage_payment_settings</code>{' '}
          permission; acting on a cashout needs the <code>process_cashouts</code> permission.
        </p>
      )}
      {overview?.warnings.map((w) => (
        <div key={w.code} role="alert" className={`flex gap-2 rounded-lg border p-3 text-sm ${w.level === 'critical'
          ? 'border-red-200 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-900/20 dark:text-red-100'
          : 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-100'}`}>
          {w.level === 'critical' ? <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" /> : <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />}
          <span>{w.message}</span>
        </div>
      ))}

      {section === 'providers' && overview && <ProvidersSection overview={overview} />}
      {section === 'nowpayments' && provider && settings && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <ProviderSettingsCard provider={provider} />
          {provider.readiness && <ReadinessCard provider={provider} />}
          <SettingsForm title="Provider settings" fields={group('provider')} settings={settings} canManage={canManage}
            busy={busy} change={change} idPrefix="provider" />
          <CredentialsCard provider={provider} canManage={canManage} busy={busy} change={change} />
          <ConnectionCard provider={provider} canManage={canManage} busy={busy} change={change} />
          {webhook && <WebhookCard webhook={webhook} />}
        </div>
      )}
      {section === 'crypto-cashout' && settings && (
        <div className="space-y-4">
          <SwitchSummary label="Automatic crypto payouts" server={settings.server_switches.crypto_auto_payout}
            effective={settings.effective.automatic_crypto_payouts}
            note="Money is sent only when the server master switch (CRYPTO_AUTO_PAYOUT_ENABLED) and the Admin switch are both on and every payout credential is configured." />
          <SettingsForm title="Crypto Cashout settings" fields={group('crypto')} settings={settings} canManage={canManage}
            busy={busy} change={change} idPrefix="crypto" />
        </div>
      )}
      {section === 'usd-cashout' && settings && (
        <div className="space-y-4">
          <SwitchSummary label="USD settlement" server={settings.server_switches.usd_settlement}
            effective={settings.effective.usd_settlement}
            note="A settlement can be recorded only when the server master switch (USD_CASHOUT_SETTLEMENT_ENABLED) and the Admin switch are both on and a settlement ledger account is chosen. No USD payment provider is configured: USD cashouts are paid outside the platform and recorded here." />
          <p className="text-sm text-gray-700 dark:text-gray-300">
            Current fee rule: <strong data-testid="usd-fee-rule">{settings.usd_fee_rule}</strong>. The fee and the net
            amount of every request are calculated on the server.
          </p>
          <SettingsForm title="USD Cashout settings" fields={group('usd')} settings={settings} canManage={canManage}
            busy={busy} change={change} idPrefix="usd" />
        </div>
      )}
      {section === 'payout-security' && settings && (
        <SettingsForm title="Payout security" fields={group('security')} settings={settings} canManage={canManage}
          busy={busy} change={change} idPrefix="security" />
      )}
      {section === 'transactions' && overview && <CashoutTransactions canProcess={canProcess} />}
      {section === 'reconciliation' && overview && <ReconciliationAndAudit canManage={canManage} />}
    </div>
  )
}

function ProvidersSection({ overview }: { overview: FinanceOverview }) {
  const s = overview.server_switches
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4 overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm text-left">
            <thead className="text-xs text-gray-500">
              <tr>
                <th className="py-2 pr-3 font-medium">Provider</th>
                <th className="py-2 pr-3 font-medium">Used for</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 font-medium">Environment</th>
                <th className="py-2 pr-3 font-medium">Pay-in</th>
                <th className="py-2 pr-3 font-medium">Payout</th>
                <th className="py-2 pr-3 font-medium">Custody</th>
                <th className="py-2 font-medium">Connection</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
              {overview.providers.map((p) => (
                <tr key={p.key}>
                  <td className="py-2 pr-3 font-medium text-gray-900 dark:text-white">{p.name}</td>
                  <td className="py-2 pr-3">{p.role}</td>
                  <td className="py-2 pr-3"><StatusPill status={p.enabled ? 'OK' : 'NOT CONFIGURED'}>{p.enabled ? 'Enabled' : 'Disabled'}</StatusPill></td>
                  <td className="py-2 pr-3">{p.environment ? humanize(p.environment) : '-'}</td>
                  <td className="py-2 pr-3">{p.payin_status ? <StatusPill status={p.payin_status} /> : '-'}</td>
                  <td className="py-2 pr-3">{p.payout_status ? <StatusPill status={p.payout_status} /> : '-'}</td>
                  <td className="py-2 pr-3">{p.custody_status ? <StatusPill status={p.custody_status} /> : '-'}</td>
                  <td className="py-2">{p.connection_status ? <StatusPill status={p.connection_status} /> : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4">
          <h2 className="font-semibold text-gray-900 dark:text-white mb-2">Safety status</h2>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <Row label="Automatic crypto payouts (effective)" value={overview.effective.automatic_crypto_payouts ? 'ACTIVE' : 'Off'} />
            <Row label="USD settlement (effective)" value={overview.effective.usd_settlement ? 'ACTIVE' : 'Off'} />
            <Row label="Server switch: crypto payouts" value={s.crypto_auto_payout ? 'On' : 'Off'} />
            <Row label="Server switch: USD settlement" value={s.usd_settlement ? 'On' : 'Off'} />
            <Row label="Credential encryption key" value={s.encryption_key_configured ? 'Configured' : 'Not configured'} />
            <Row label="Payment callbacks (IPN)" value={webhookStatusLabel(overview.webhook_status)} />
            <Row label="Configuration version" value={String(overview.configuration_version)} />
          </dl>
        </CardContent>
      </Card>
    </div>
  )
}

function SwitchSummary({ label, server, effective, note }: { label: string; server: boolean; effective: boolean; note: string }) {
  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-semibold text-gray-900 dark:text-white">{label}</span>
          <StatusPill status={effective ? 'OK' : 'NOT CONFIGURED'}>{effective ? 'Active' : 'Not active'}</StatusPill>
          <span className="text-gray-500">Server master switch: {server ? 'On' : 'Off'}</span>
        </div>
        <p className="text-xs text-gray-500">{note}</p>
      </CardContent>
    </Card>
  )
}

function ProviderSettingsCard({ provider }: { provider: ProviderView }) {
  return (
    <Card>
      <CardContent className="p-4">
        <h2 className="font-semibold text-gray-900 dark:text-white mb-2">{provider.display_name}</h2>
        <dl className="space-y-2 text-sm">
          <Row label="Status" value={provider.enabled ? 'Enabled' : 'Disabled'} />
          <Row label="Environment (set on the server)" value={humanize(provider.environment)} />
          <Row label="Pay-in configuration" value={<StatusPill status={provider.payin_status} />} />
          <Row label="Custody configuration" value={<StatusPill status={provider.custody_status} />} />
          <Row label="Payout configuration" value={<StatusPill status={provider.payout_status} />} />
          <Row label="Supported payout currency" value={provider.payout_currency} />
          <Row label="Supported payout network" value={provider.payout_network} />
          <Row label="Connection" value={<StatusPill status={provider.connection.status} />} />
          <Row label="Last successful connection test" value={dateTime(provider.connection.last_success_at)} />
          <Row label="Last configuration update" value={dateTime(provider.last_configuration_update)} />
        </dl>
      </CardContent>
    </Card>
  )
}

export function SettingsForm({ title, fields, settings, canManage, busy, change, idPrefix }: {
  title: string; fields: SettingField[]; settings: FinanceSettings; canManage: boolean; busy: boolean
  change: Change; idPrefix: string
}) {
  const initial = useMemo(() => Object.fromEntries(fields.map((f) =>
    [f.name, f.kind === 'bool' ? Boolean(f.value) : String(f.value ?? '')])), [fields])
  const [draft, setDraft] = useState<Record<string, string | boolean>>(initial)
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  useEffect(() => { setDraft(initial) }, [initial])

  const changes = changedValues(fields, draft)
  // Switching on something that moves money needs a typed confirmation phrase.
  const phrase = Object.keys(changes).map((name) => changes[name] === true ? settings.confirmations[name] : undefined)
    .find(Boolean)
  const disabled = !canManage || busy

  const save = async () => {
    const sentPassword = password
    setPassword('')
    const ok = await change(() => api.put(`${FINANCE_BASE}/settings`, {
      changes, current_password: sentPassword, confirmation: phrase ? confirmation : undefined,
    }), `${title} saved. Nothing was paid or released by this change.`, `${title} could not be saved.`)
    if (ok) setConfirmation('')
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-4">
        <h2 className="font-semibold text-gray-900 dark:text-white">{title}</h2>
        {fields.map((f) => {
          const id = `${idPrefix}-${f.name}`
          return (
            <div key={f.name} className="space-y-1">
              <div className="flex items-start justify-between gap-3">
                <label htmlFor={id} className="text-sm font-medium text-gray-900 dark:text-white">{f.label}</label>
                {f.kind === 'bool' && (
                  <Switch id={id} aria-label={f.label} checked={Boolean(draft[f.name])} disabled={disabled}
                    onCheckedChange={(v) => setDraft({ ...draft, [f.name]: v })} />
                )}
              </div>
              {f.kind === 'choice' && (
                <select id={id} className={inputClass} value={String(draft[f.name] ?? '')} disabled={disabled}
                  onChange={(e) => setDraft({ ...draft, [f.name]: e.target.value })}>
                  {f.choices.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
                </select>
              )}
              {!['bool', 'choice'].includes(f.kind) && (
                <div className="flex items-center gap-2">
                  <input id={id} className={inputClass} value={String(draft[f.name] ?? '')} disabled={disabled}
                    inputMode={['text', 'account'].includes(f.kind) ? 'text' : 'decimal'} maxLength={f.max_length ?? 20}
                    onChange={(e) => setDraft({ ...draft, [f.name]: e.target.value })} />
                  {f.unit && <span className="text-xs text-gray-500 whitespace-nowrap">{f.unit}</span>}
                </div>
              )}
              <p className="text-xs text-gray-500">
                {f.help}
                {f.minimum !== null && f.maximum !== null && ` Allowed: ${f.minimum} to ${f.maximum}.`}
              </p>
              {f.approval_note && (
                <p className="text-xs text-amber-700 dark:text-amber-300" data-testid={`approval-${f.name}`}>{f.approval_note}</p>
              )}
            </div>
          )
        })}
        {canManage && (
          <div className="space-y-3 pt-3 border-t border-gray-200 dark:border-gray-700">
            {phrase && (
              <div className="space-y-1">
                <label htmlFor={`${idPrefix}-confirmation`} className="block text-sm font-medium text-red-700 dark:text-red-300">
                  Type &quot;{phrase}&quot; to confirm
                </label>
                <input id={`${idPrefix}-confirmation`} className={inputClass} value={confirmation} disabled={busy}
                  autoComplete="off" onChange={(e) => setConfirmation(e.target.value)} />
              </div>
            )}
            <PasswordField id={`${idPrefix}-password`} value={password} onChange={setPassword} disabled={busy} />
            <Button onClick={() => void save()}
              disabled={busy || !password || Object.keys(changes).length === 0 || (!!phrase && confirmation !== phrase)}>
              Save changes
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function CredentialsCard({ provider, canManage, busy, change }: {
  provider: ProviderView; canManage: boolean; busy: boolean; change: Change
}) {
  // Write-only: never pre-filled, cleared as soon as it has been sent.
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [password, setPassword] = useState('')
  const [deleting, setDeleting] = useState<string | null>(null)
  const payload = credentialPayload(draft)
  const locked = !canManage || busy || !provider.encryption_key_configured

  const store = async () => {
    const values = payload
    const sentPassword = password
    setDraft({})
    setPassword('')
    await change(() => api.put(`${FINANCE_BASE}/credentials`, { values, current_password: sentPassword }),
      'Credentials stored encrypted. They cannot be shown again.', 'The credentials could not be stored.')
  }

  const remove = async (name: string) => {
    const sentPassword = password
    setPassword('')
    setDeleting(null)
    await change(() => api.post(`${FINANCE_BASE}/credentials/${name}/delete`, { current_password: sentPassword }),
      'The stored credential was deleted.', 'The credential could not be deleted.')
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <h2 className="font-semibold text-gray-900 dark:text-white">API credentials</h2>
        <p className="text-xs text-gray-500">
          Stored encrypted and never shown again. Leave a field blank to keep its stored value. The credentials in use
          come from the source selected in Provider settings (pay-in: {humanize(provider.credential_sources.payin)},
          payout: {humanize(provider.credential_sources.payout)}); the two sources are never mixed.
          {!provider.encryption_key_configured && ' The server has no PAYMENT_SETTINGS_ENCRYPTION_KEY, so nothing can be stored here.'}
        </p>
        {provider.credentials.map((c) => (
          <div key={c.name} className="space-y-1 border-t border-gray-100 dark:border-gray-700 pt-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label htmlFor={`credential-${c.name}`} className="text-sm font-medium">{c.label}</label>
              <span className="flex items-center gap-2 text-xs text-gray-500" data-testid={`credential-status-${c.name}`}>
                In use: <StatusPill status={c.in_use} />
                Stored: <StatusPill status={c.stored_readable === false ? 'UNREADABLE' : c.stored} />
              </span>
            </div>
            <input id={`credential-${c.name}`} type="password" autoComplete="new-password" className={inputClass}
              placeholder={c.stored === 'CONFIGURED' ? 'Leave blank to keep the stored value' : 'Not stored'}
              value={draft[c.name] ?? ''} disabled={locked}
              onChange={(e) => setDraft({ ...draft, [c.name]: e.target.value })} />
            {c.stored === 'CONFIGURED' && canManage && (
              deleting === c.name ? (
                <span className="flex flex-wrap items-center gap-2 text-xs">
                  Delete this stored credential? Enter your password below, then
                  <Button size="sm" variant="outline" disabled={busy || !password} onClick={() => void remove(c.name)}>
                    Confirm delete
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setDeleting(null)}>Cancel</Button>
                </span>
              ) : (
                <button type="button" className="text-xs text-red-600 underline" disabled={busy}
                  onClick={() => setDeleting(c.name)}>
                  Delete stored {c.label.toLowerCase()}
                </button>
              )
            )}
          </div>
        ))}
        {canManage && (
          <div className="space-y-3 pt-3 border-t border-gray-200 dark:border-gray-700">
            <PasswordField id="credentials-password" value={password} onChange={setPassword} disabled={busy} />
            <Button onClick={() => void store()} disabled={locked || !password || Object.keys(payload).length === 0}>
              Store credentials
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

const READINESS_LEGEND: Record<string, string> = {
  VERIFIED: 'a check against the provider succeeded with the current credentials',
  CONFIGURED: 'credentials are present; nothing has proven that they work',
  UNVERIFIED: 'not configured, or not determinable yet',
  BLOCKED: 'the provider refused; see the reason',
  DISABLED: 'switched off here',
}

/**
 * What is proven, what is only configured and what the provider refused. The
 * server builds it from the last connection test, the callback counters and
 * the configuration; this card only displays it and has no action.
 */
function ReadinessCard({ provider }: { provider: ProviderView }) {
  const readiness = provider.readiness
  if (!readiness) return null
  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <h2 className="font-semibold text-gray-900 dark:text-white">Provider status</h2>
        <ul className="text-sm space-y-2" data-testid="provider-readiness">
          {readiness.items.map((item) => (
            <li key={item.key} data-testid={`readiness-${item.key}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-gray-900 dark:text-white">{item.label}</span>
                <TonePill tone={readinessTone(item.state)}>{humanize(item.state)}</TonePill>
              </div>
              <p className="text-xs text-gray-500">{item.detail}</p>
            </li>
          ))}
        </ul>
        <dl className="text-sm space-y-1 border-t border-gray-100 dark:border-gray-700 pt-2">
          <Row label="Payout currency / network" value={`${provider.payout_currency} / ${provider.payout_network}`} />
          <Row label="Last connection test" value={dateTime(readiness.last_test_at)} />
          <Row label="Last successful connection test" value={dateTime(readiness.last_success_at)} />
        </dl>
        {readiness.last_error && (
          <p className="text-sm text-red-700 dark:text-red-300" data-testid="provider-last-error">
            Last provider error ({checkLabel(readiness.last_error.check)}, {dateTime(readiness.last_error.at)}):{' '}
            {readiness.last_error.message}
          </p>
        )}
        {readiness.outstanding.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-gray-900 dark:text-white">Outstanding requirements</h3>
            <ul className="list-disc pl-5 text-xs text-gray-600 dark:text-gray-300 space-y-1"
              data-testid="provider-outstanding">
              {readiness.outstanding.map((line) => <li key={line}>{line}</li>)}
            </ul>
          </div>
        )}
        <p className="text-xs text-gray-500">
          {readiness.states.map((state) => `${humanize(state)}: ${READINESS_LEGEND[state] ?? ''}`).join('. ')}.
        </p>
      </CardContent>
    </Card>
  )
}

function ConnectionCard({ provider, canManage, busy, change }: {
  provider: ProviderView; canManage: boolean; busy: boolean; change: Change
}) {
  const c = provider.connection
  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold text-gray-900 dark:text-white">Connection test</h2>
          <StatusPill status={c.status} />
        </div>
        <p className="text-xs text-gray-500">
          Read-only: it reads the provider status, the supported currencies, the custody balance, the payout
          minimum and the network fee estimate, and checks that the payout login is accepted (the session is
          discarded at once). It creates no payment, starts no payout and moves no funds. The second factor cannot
          be verified without a real payout and is not tested here.
        </p>
        <p className="text-sm" data-testid="connection-message">{c.message}</p>
        {c.checks.length > 0 && (
          <ul className="text-sm space-y-1">
            {c.checks.map((check) => (
              <li key={check.name} className="flex flex-wrap items-center justify-between gap-2">
                <span>{checkLabel(check.name)}</span>
                <span className="flex items-center gap-2 text-xs text-gray-500">
                  {check.status !== 'OK' && check.message}<StatusPill status={check.status} />
                </span>
              </li>
            ))}
          </ul>
        )}
        {Object.keys(c.facts).length > 0 && (
          <dl className="text-sm space-y-1 border-t border-gray-100 dark:border-gray-700 pt-2">
            {c.facts.custody_balance !== undefined && <Row label={`Custody balance (${provider.payout_currency})`} value={c.facts.custody_balance} />}
            {c.facts.custody_pending !== undefined && <Row label="Custody amount being processed" value={c.facts.custody_pending} />}
            {c.facts.payout_minimum !== undefined && <Row label="Provider payout minimum" value={c.facts.payout_minimum} />}
            {c.facts.network_fee !== undefined && <Row label="Network fee estimate" value={c.facts.network_fee} />}
          </dl>
        )}
        <p className="text-xs text-gray-500">Last test: {dateTime(c.tested_at)}</p>
        {canManage && (
          <Button variant="outline" disabled={busy}
            onClick={() => void change(() => api.post(`${FINANCE_BASE}/connection-test`, {}),
              'Connection test finished.', 'The connection test could not be run.')}>
            Run connection test
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

function WebhookCard({ webhook }: { webhook: WebhookHealth }) {
  const counts = webhook.last_7_days
  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold text-gray-900 dark:text-white">Callback / IPN</h2>
          <StatusPill status={webhook.status}>{webhookStatusLabel(webhook.status)}</StatusPill>
        </div>
        <dl className="space-y-2 text-sm">
          <div>
            <dt className="text-gray-500">Callback URL (derived from the server address; not editable)</dt>
            <dd className="font-mono text-xs break-all" data-testid="callback-url">{webhook.callback_url}</dd>
          </div>
          <Row label="Accepted (7 days)" value={counts.ACCEPTED ?? 0} />
          <Row label="Rejected: invalid signature (7 days)" value={counts.REJECTED_SIGNATURE ?? 0} />
          <Row label="Unknown order (7 days)" value={counts.UNKNOWN_ORDER ?? 0} />
          <Row label="Payout notifications (7 days)" value={webhook.payout_notices_7_days ?? 0} />
          <Row label="Last accepted" value={dateTime(webhook.last_accepted_at)} />
          <Row label="Last valid signature" value={dateTime(webhook.last_verified_signature_at)} />
          <Row label="Last signature rejection" value={dateTime(webhook.last_signature_rejection_at)} />
        </dl>
        <p className="text-xs text-gray-500">{webhook.signature_verification}</p>
        {!webhook.callback_url_secure && (
          <p className="text-xs text-red-600">The callback URL is not HTTPS. Set the public server address before going live.</p>
        )}
      </CardContent>
    </Card>
  )
}
