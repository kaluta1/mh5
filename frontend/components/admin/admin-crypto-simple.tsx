'use client'

import { useState } from 'react'

import api from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { FINANCE_BASE } from '@/lib/finance-admin'
import { Row, TonePill, inputClass } from './admin-finance-ui'

/** GET /admin/finance/crypto-summary: the owner's Crypto Cashout settings in plain terms. Read-only. */
export type CryptoSummary = {
  version: number
  minimum_usd: string
  member_pays_fee: boolean
  fee_mode: string
  required_fee_mode: string
  fee_mode_confirmed: boolean
  fee_cap_usd: string
  fee_cap_percent: string
  max_network_fee_percent: string
  margin_percent: string | null
  min_net_payout_usd: string
  approved: boolean
  approval_blocked_by: { code: string; message: string } | null
  automatic_payouts: { admin_switch: boolean; server_switch: boolean }
  preview: null | {
    amount: string; network_fee: string; fee_checked: string | null; member_receives: string | null
    provider_debit: string | null; provider_minimum: string; read_at: string
  }
}

type Change = (request: () => Promise<{ status: number; data?: any }>, ok: string, failure: string,
  onRefused?: (message: string, field: string | null) => void) => Promise<boolean>

const AMOUNT = /^\d+(\.\d{1,2})?$/

/** Highest fee the configuration allows on a payout of `gross` (the lower limit that is set), or null. */
function feeLimit(gross: number, capUsd: number, capPercent: number): number | null {
  const limits = [capUsd > 0 ? capUsd : null, capPercent > 0 ? (gross * capPercent) / 100 : null]
    .filter((v): v is number => v !== null)
  return limits.length ? Math.min(...limits) : null
}

function Password({ id, value, onChange, disabled }: {
  id: string; value: string; onChange: (value: string) => void; disabled: boolean
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">Your password</label>
      <input id={id} type="password" autoComplete="current-password" className={inputClass} value={value}
        disabled={disabled} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

/**
 * Admin > Finance & Payments > Crypto Cashout, the simple view: the settings the owner decides, the
 * password, Save Settings and, when needed, Approve Settings. The server still checks everything: the
 * permissions, the password, the version shown, and the approval as a change of its own. Nothing here
 * can switch automatic payouts on.
 */
export default function SimpleCryptoSettings({ summary, canManage, canActivate, busy, change }: {
  summary: CryptoSummary; canManage: boolean; canActivate: boolean; busy: boolean; change: Change
}) {
  const [cap, setCap] = useState(summary.fee_cap_usd)
  const [savePassword, setSavePassword] = useState('')
  const [approvePassword, setApprovePassword] = useState('')
  const [refusal, setRefusal] = useState<{ step: 'save' | 'approve'; message: string } | null>(null)

  const capValid = AMOUNT.test(cap.trim()) && Number(cap) > 0
  const changes: Record<string, string> = {}
  // SoncoPay adds its fee on top of the amount sent: saving records that behaviour with the settings.
  if (!summary.fee_mode_confirmed) changes.provider_fee_mode = summary.required_fee_mode
  if (!summary.member_pays_fee) changes.network_fee_policy = 'MEMBER_PAYS'
  if (capValid && Number(cap) !== Number(summary.fee_cap_usd)) changes.member_fee_cap_usd = Number(cap).toFixed(2)
  const pending = Object.keys(changes).length > 0
  const auto = summary.automatic_payouts.admin_switch && summary.automatic_payouts.server_switch

  const preview = summary.preview
  const limit = preview ? feeLimit(Number(preview.amount), capValid ? Number(cap) : 0, Number(summary.fee_cap_percent)) : null
  const tooLow = preview?.fee_checked != null && limit !== null && Number(preview.fee_checked) > limit

  const save = async () => {
    const password = savePassword
    setSavePassword('')
    setRefusal(null)
    await change(() => api.put(`${FINANCE_BASE}/settings`, {
      changes, current_password: password, expected_version: summary.version,
    }), 'Settings saved.', 'The settings could not be saved.', (message) => setRefusal({ step: 'save', message }))
  }

  const approve = async () => {
    const password = approvePassword
    setApprovePassword('')
    setRefusal(null)
    await change(() => api.put(`${FINANCE_BASE}/settings`, {
      changes: { fee_terms_approved: true }, current_password: password, expected_version: summary.version,
    }), 'Settings approved.', 'The settings could not be approved.', (message) => setRefusal({ step: 'approve', message }))
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-4" data-testid="crypto-simple">
        <h2 className="font-semibold text-gray-900 dark:text-white">Crypto cashout settings</h2>

        <dl className="space-y-2 text-sm">
          <Row label="Minimum cashout" value={<span data-testid="simple-minimum">${summary.minimum_usd}</span>} />
          <Row label="Network fee" value={<span data-testid="simple-fee-payer">{summary.member_pays_fee ? 'Member pays' : 'Not set'}</span>} />
          <Row label="Automatic payouts" value={
            <span data-testid="simple-auto"><TonePill tone={auto ? 'green' : 'gray'}>{auto ? 'ON' : 'OFF'}</TonePill></span>} />
        </dl>

        <div className="space-y-1">
          <label htmlFor="simple-cap" className="block text-sm font-medium">Maximum network fee (USD)</label>
          <input id="simple-cap" className={inputClass} inputMode="decimal" maxLength={10} value={cap}
            disabled={!canManage || busy} onChange={(e) => setCap(e.target.value)} />
          {!capValid && <p role="alert" className="text-xs text-red-600">Enter an amount above 0, for example 0.50.</p>}
          {capValid && tooLow && (
            <p role="alert" className="text-xs text-red-600" data-testid="simple-too-low">
              Too low: a ${preview!.amount} cashout needs at least {preview!.fee_checked}.
            </p>
          )}
        </div>

        {preview?.member_receives && (
          <p className="text-sm text-gray-600 dark:text-gray-400" data-testid="simple-preview">
            Example: a ${preview.amount} cashout pays the member {preview.member_receives} USDT (network fee {preview.network_fee}).
          </p>
        )}

        {canManage && (
          <div className="space-y-3 pt-3 border-t border-gray-200 dark:border-gray-700">
            <Password id="simple-save-password" value={savePassword} onChange={setSavePassword} disabled={busy} />
            {refusal?.step === 'save' && <p role="alert" className="text-sm text-red-600" data-testid="simple-save-error">{refusal.message}</p>}
            <Button onClick={() => void save()} disabled={busy || !pending || !savePassword || !capValid}>
              Save Settings
            </Button>
            {!pending && <p className="text-xs text-gray-500" data-testid="simple-saved">No changes to save.</p>}
          </div>
        )}

        {canManage && !pending && (
          <div className="space-y-3 pt-3 border-t border-gray-200 dark:border-gray-700" data-testid="simple-approval">
            {summary.approved
              ? <p className="text-sm text-green-700 dark:text-green-400" data-testid="simple-approved">Settings approved.</p>
              : summary.approval_blocked_by
                ? <p className="text-sm text-amber-800 dark:text-amber-200" data-testid="simple-approve-blocked">
                    Cannot be approved yet: {summary.approval_blocked_by.message}
                  </p>
                : !canActivate
                  ? <p className="text-sm text-amber-800 dark:text-amber-200" data-testid="simple-approve-permission">
                      Your account is not allowed to approve these settings.
                    </p>
                  : <>
                    <p className="text-sm text-gray-700 dark:text-gray-300">The settings are saved. Approve them to use them.</p>
                    <Password id="simple-approve-password" value={approvePassword} onChange={setApprovePassword} disabled={busy} />
                    {refusal?.step === 'approve' && <p role="alert" className="text-sm text-red-600" data-testid="simple-approve-error">{refusal.message}</p>}
                    <Button onClick={() => void approve()} disabled={busy || !approvePassword}>Approve Settings</Button>
                  </>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
