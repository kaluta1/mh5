/**
 * Manually recorded payments: two administrators (maker-checker).
 *
 * Step 1: an administrator RECORDS a payment received outside the payment
 * provider (POST /admin/users/{id}/grant-payment). Nothing is credited yet.
 * Step 2: a DIFFERENT administrator CONFIRMS that the money was received,
 * citing where (evidence reference); only then is the payment credited,
 * posted and commissioned. The server enforces every rule; the page only
 * keeps the buttons honest.
 */

export const MANUAL_PAYMENTS_URL = '/api/v1/admin/manual-payments'
export const manualPaymentActionUrl = (id: number, action: 'confirm' | 'reject' | 'cancel') =>
  `${MANUAL_PAYMENTS_URL}/${id}/${action}`

export const EVIDENCE_MIN_LENGTH = 6
export const DECISION_REASON_MIN_LENGTH = 10

export type ManualPayment = {
  id: number
  deposit_id: number
  member_id: number
  product_code: string
  amount: string
  currency: string
  status: 'REQUESTED' | 'CONFIRMED' | 'REJECTED' | 'CANCELLED'
  created_new_deposit: boolean
  verify_identity_requested: boolean
  requested_by: number
  requested_at: string | null
  request_reason: string
  decided_by: number | null
  decided_at: string | null
  evidence_reference: string | null
  decision_note: string | null
  member?: { id: number; username: string | null; full_name: string | null; email: string }
}

export type ManualPaymentList = { items: ManualPayment[]; current_admin_id: number; can_decide: boolean }

const words = (text: string) => text.split(/\s+/).filter(Boolean).join(' ')

export const validEvidence = (text: string) => words(text).length >= EVIDENCE_MIN_LENGTH
export const validDecisionReason = (text: string) => words(text).length >= DECISION_REASON_MIN_LENGTH

/** What the signed-in administrator may do with one open request. */
export function allowedActions(item: ManualPayment, currentAdminId: number, canDecide: boolean) {
  const open = item.status === 'REQUESTED'
  const mine = item.requested_by === currentAdminId
  const isMember = item.member_id === currentAdminId
  return {
    confirm: open && canDecide && !mine && !isMember,
    reject: open && canDecide && !mine && !isMember,
    cancel: open && mine,
    waitingForSecondAdmin: open && mine,
  }
}
