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

function Secret({ id, value, onChange, disabled }: {
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

function Phrase({ id, phrase, value, onChange, disabled }: {
  id: string; phrase: string; value: string; onChange: (value: string) => void; disabled: boolean
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium">
        Type <span className="font-mono">{phrase}</span> to confirm
      </label>
      <input id={id} className={inputClass} value={value} disabled={disabled} autoComplete="off"
        onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

/**
 * Admin > Finance & Payments > Crypto Cashout, the simple view: the four settings the owner decides,
 * a payout preview, and two steps (save, then approve). Every rule stays on the server: the same
 * PUT /settings with the password, the typed phrase and the version shown, and the approval in a change
 * of its own. Nothing here can switch automatic payouts on.
 */
export default function SimpleCryptoSettings({ summary, confirmations, canManage, canActivate, busy, change }: {
  summary: CryptoSummary; confirmations: Record<string, string>; canManage: boolean; canActivate: boolean
  busy: boolean; change: Change
}) {
  const [cap, setCap] = useState(summary.fee_cap_usd)
  const [savePassword, setSavePassword] = useState('')
  const [savePhrase, setSavePhrase] = useState('')
  const [approvePassword, setApprovePassword] = useState('')
  const [approvePhrase, setApprovePhrase] = useState('')
  const [refusal, setRefusal] = useState<{ step: 1 | 2; message: string } | null>(null)

  const capValid = AMOUNT.test(cap.trim()) && Number(cap) > 0
  const changes: Record<string, string> = {}
  if (!summary.fee_mode_confirmed) changes.provider_fee_mode = summary.required_fee_mode
  if (!summary.member_pays_fee) changes.network_fee_policy = 'MEMBER_PAYS'
  if (capValid && Number(cap) !== Number(summary.fee_cap_usd)) changes.member_fee_cap_usd = Number(cap).toFixed(2)
  const pending = Object.keys(changes).length > 0
  const modePhrase = changes.provider_fee_mode ? confirmations.provider_fee_mode : undefined
  const approvalPhrase = confirmations.fee_terms_approved
  const auto = summary.automatic_payouts.admin_switch && summary.automatic_payouts.server_switch

  const preview = summary.preview
  const limit = preview ? feeLimit(Number(preview.amount), capValid ? Number(cap) : 0, Number(summary.fee_cap_percent)) : null
  const withinLimit = preview?.fee_checked != null && limit !== null ? Number(preview.fee_checked) <= limit : null

  const save = async () => {
    const password = savePassword
    setSavePassword('')
    setRefusal(null)
    const ok = await change(() => api.put(`${FINANCE_BASE}/settings`, {
      changes, current_password: password, confirmation: modePhrase ? savePhrase : undefined,
      expected_version: summary.version,
    }), 'Settings saved. Now approve them in step 2. Nothing was paid by this change.',
    'The settings could not be saved.', (message) => setRefusal({ step: 1, message }))
    if (ok) setSavePhrase('')
  }

  const approve = async () => {
    const password = approvePassword
    setApprovePassword('')
    setRefusal(null)
    const ok = await change(() => api.put(`${FINANCE_BASE}/settings`, {
      changes: { fee_terms_approved: true }, current_password: password, confirmation: approvePhrase,
      expected_version: summary.version,
    }), 'Fee settings approved. Automatic payouts are still off; nothing was paid.',
    'The fee settings could not be approved.', (message) => setRefusal({ step: 2, message }))
    if (ok) setApprovePhrase('')
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-5" data-testid="crypto-simple">
        <div>
          <h2 className="font-semibold text-gray-900 dark:text-white">Crypto cashout settings</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">Members are paid in USDT. These are the settings you decide.</p>
        </div>

        <dl className="space-y-2 text-sm">
          <Row label="Minimum cashout" value={<span data-testid="simple-minimum">${summary.minimum_usd}</span>} />
          <Row label="Network fee" value={<span data-testid="simple-fee-payer">{summary.member_pays_fee ? 'Member pays' : 'Not set to member pays'}</span>} />
          <Row label="Automatic payouts" value={
            <span data-testid="simple-auto"><TonePill tone={auto ? 'green' : 'gray'}>{auto ? 'ON' : 'OFF'}</TonePill></span>} />
          <Row label="Fee settings" value={
            <span data-testid="simple-approval">
              <TonePill tone={summary.approved ? 'green' : 'amber'}>{summary.approved ? 'Approved' : 'Not approved yet'}</TonePill>
            </span>} />
        </dl>

        <div className="space-y-1">
          <label htmlFor="simple-cap" className="block text-sm font-medium">Maximum network fee per payout (USD)</label>
          <input id="simple-cap" className={inputClass} inputMode="decimal" maxLength={10} value={cap}
            disabled={!canManage || busy} onChange={(e) => setCap(e.target.value)} />
          {!capValid && <p role="alert" className="text-xs text-red-600">Enter an amount above 0, for example 0.50.</p>}
          <p className="text-xs text-gray-500">A payout is held when its network fee would be higher than this.</p>
        </div>

        <p className="text-sm text-gray-700 dark:text-gray-300" data-testid="simple-fee-rule">
          SoncoPay adds its network fee on top of the amount it sends. MyHigh5 therefore sends the payout minus
          that fee, so the member pays the fee and MyHigh5 never does.
        </p>

        {preview && preview.member_receives && (
          <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 text-sm space-y-1" data-testid="simple-preview">
            <p className="font-medium text-gray-900 dark:text-white">Example: a ${preview.amount} cashout</p>
            <dl className="space-y-1">
              <Row label="Member receives" value={`${preview.member_receives} USDT`} />
              <Row label="SoncoPay network fee" value={`${preview.network_fee} USDT`} />
              <Row label="Taken from the SoncoPay balance" value={`${preview.provider_debit} USDT`} />
            </dl>
            {withinLimit !== null && (
              <p className={withinLimit ? 'text-green-700 dark:text-green-400' : 'text-red-600'} data-testid="simple-preview-limit">
                {withinLimit
                  ? `Within your maximum fee: the fee with its safety margin is ${preview.fee_checked}, the limit is ${limit!.toFixed(2)}.`
                  : `Above your maximum fee: the fee with its safety margin is ${preview.fee_checked}, the limit is ${limit!.toFixed(2)}. This payout would be held. Raise the maximum network fee.`}
              </p>
            )}
          </div>
        )}
        {!preview && (
          <p className="text-xs text-gray-500" data-testid="simple-no-preview">
            The example appears once the SoncoPay fee has been read.
          </p>
        )}

        {!canManage && (
          <p className="text-sm text-gray-600 dark:text-gray-400">You can view these settings but not change them.</p>
        )}

        {canManage && (
          <section className="space-y-3 pt-3 border-t border-gray-200 dark:border-gray-700" aria-labelledby="simple-step1">
            <h3 id="simple-step1" className="text-sm font-semibold">Step 1: Save settings</h3>
            {!pending
              ? <p className="text-sm text-gray-600 dark:text-gray-400" data-testid="simple-step1-done">Nothing to save. The settings above are in force.</p>
              : <>
                {modePhrase && (
                  <>
                    <p className="text-xs text-gray-500">
                      Saving also records that SoncoPay adds its fee on top of the amount sent, as SoncoPay documents.
                    </p>
                    <Phrase id="simple-save-phrase" phrase={modePhrase} value={savePhrase} onChange={setSavePhrase} disabled={busy} />
                  </>
                )}
                <Secret id="simple-save-password" value={savePassword} onChange={setSavePassword} disabled={busy} />
                {refusal?.step === 1 && <p role="alert" className="text-sm text-red-600" data-testid="simple-save-error">Not saved: {refusal.message}</p>}
                <Button onClick={() => void save()}
                  disabled={busy || !savePassword || !capValid || (!!modePhrase && savePhrase.trim() !== modePhrase)}>
                  Save settings
                </Button>
                {summary.approved && <p className="text-xs text-gray-500">Saving a change withdraws the approval; approve again in step 2.</p>}
              </>}
          </section>
        )}

        {canManage && (
          <section className="space-y-3 pt-3 border-t border-gray-200 dark:border-gray-700" aria-labelledby="simple-step2">
            <h3 id="simple-step2" className="text-sm font-semibold">Step 2: Approve fee settings</h3>
            {summary.approved
              ? <p className="text-sm text-green-700 dark:text-green-400" data-testid="simple-approved">The fee settings are approved.</p>
              : pending
                ? <p className="text-sm text-gray-600 dark:text-gray-400" data-testid="simple-approve-wait">Save step 1 first. Approval is a separate step.</p>
                : summary.approval_blocked_by
                  ? <p className="text-sm text-amber-800 dark:text-amber-200" data-testid="simple-approve-blocked">
                      Cannot be approved yet: {summary.approval_blocked_by.message} Open Advanced settings below to fix it.
                    </p>
                  : !canActivate
                    ? <p className="text-sm text-amber-800 dark:text-amber-200" data-testid="simple-approve-permission">
                        Approving needs the activate_financial_operations permission, which your account does not have.
                      </p>
                    : <>
                      <p className="text-xs text-gray-500">
                        Approving lets members accept these fee terms. It does not switch automatic payouts on.
                      </p>
                      <Phrase id="simple-approve-phrase" phrase={approvalPhrase} value={approvePhrase} onChange={setApprovePhrase} disabled={busy} />
                      <Secret id="simple-approve-password" value={approvePassword} onChange={setApprovePassword} disabled={busy} />
                      {refusal?.step === 2 && <p role="alert" className="text-sm text-red-600" data-testid="simple-approve-error">Not approved: {refusal.message}</p>}
                      <Button onClick={() => void approve()}
                        disabled={busy || !approvePassword || approvePhrase.trim() !== approvalPhrase}>
                        Approve fee settings
                      </Button>
                    </>}
          </section>
        )}

        <p className="text-xs text-gray-500">
          Automatic payouts stay OFF. Nothing on this card switches them on or sends money.
        </p>
      </CardContent>
    </Card>
  )
}
