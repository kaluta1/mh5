import api from '@/lib/api'

/** Marketplace seller registration (separate from member KYC). MyHigh5 approval is permission to sell on
 * MyHigh5 only: never a government registration, tax registration or licence. */

export type SellerCategory = 'PRIVATE' | 'SOLE_TRADER' | 'ORGANISATION'

export type SellerApplicationStatus =
  | 'DRAFT' | 'SUBMITTED' | 'CHECKS_IN_PROGRESS' | 'ACTION_REQUIRED' | 'MANUAL_REVIEW_REQUIRED'
  | 'APPROVED' | 'REJECTED' | 'RESTRICTED' | 'REVERIFICATION_REQUIRED' | 'SUPERSEDED'

export type Licence = { type: string; authority: string; number: string; expires_on: string | null }
export type Owner = { full_name: string; percent: string }

export type SellerApplicationInput = {
  seller_category: SellerCategory
  business_structure?: string | null
  legal_name?: string | null
  trading_name?: string | null
  residence_country?: string | null
  establishment_country?: string | null
  establishment_subdivision?: string | null
  customer_markets?: string[]
  business_address?: string | null
  contact_phone?: string | null
  product_categories?: string[]
  products_description?: string | null
  commercial_indicators?: Record<string, boolean>
  registration_authority?: string | null
  registration_number?: string | null
  exemption_basis?: string | null
  tax_registered?: boolean | null
  tax_identifier?: string | null
  licences?: Licence[]
  representative?: { full_name: string | null; role: string | null } | null
  ownership?: Owner[]
}

export type SellerDocument = { id: number; doc_type: string; file_name: string; size: number; expires_on: string | null }

export type SellerApplication = Omit<SellerApplicationInput, 'tax_identifier'> & {
  id: number
  status: SellerApplicationStatus
  tax_identifier_masked: string | null
  declaration_accepted_at: string | null
  submitted_at: string | null
  decided_at: string | null
  correction_request: string | null
  missing_fields: string[]
  documents: SellerDocument[]
  history: { to_status: string; at: string | null; message: string | null }[]
  review_status_message?: string | null
}

export type SellerStatus = {
  enforcement_enabled: boolean
  can_sell: boolean
  profile: { status: string; seller_category: SellerCategory | null; public_label: string | null; reverify_due_at: string | null }
  application: SellerApplication | null
  declaration: { version: string; text: string }
  product_categories: string[]
  regulated_categories: string[]
  private_review_thresholds: { sales_usd: string; order_count: number; note: string }
}

const S = '/api/v1/marketplace/seller'

export async function getSellerStatus(): Promise<SellerStatus> {
  return (await api.get<SellerStatus>(`${S}/status`)).data
}

export async function saveSellerApplication(input: SellerApplicationInput): Promise<SellerStatus> {
  return (await api.put<SellerStatus>(`${S}/application`, input)).data
}

export async function submitSellerApplication(declarationVersion: string): Promise<SellerStatus> {
  return (await api.post<SellerStatus>(`${S}/application/submit`, {
    declaration_version: declarationVersion, accept_declaration: true })).data
}

export async function uploadSellerDocument(docType: string, file: File, expiresOn?: string): Promise<SellerStatus> {
  const form = new FormData()
  form.append('doc_type', docType)
  if (expiresOn) form.append('expires_on', expiresOn)
  form.append('file', file)
  return (await api.post<SellerStatus>(`${S}/application/documents`, form, {
    headers: { 'Content-Type': 'multipart/form-data' } })).data
}

export async function appealSellerDecision(text: string): Promise<SellerStatus> {
  return (await api.post<SellerStatus>(`${S}/appeal`, { text })).data
}

export const SELLER_STATUS_LABEL: Record<string, string> = {
  NONE: 'Not registered',
  DRAFT: 'Draft',
  SUBMITTED: 'Submitted',
  CHECKS_IN_PROGRESS: 'Automated checks in progress',
  ACTION_REQUIRED: 'Action required',
  MANUAL_REVIEW_REQUIRED: 'Manual review',
  APPROVED: 'Approved to sell on MyHigh5',
  REJECTED: 'Not approved',
  RESTRICTED: 'Selling restricted',
  REVERIFICATION_REQUIRED: 'Reverification required',
  SUPERSEDED: 'Replaced by a newer application',
}

export const CATEGORY_LABEL: Record<SellerCategory, string> = {
  PRIVATE: 'Private Seller',
  SOLE_TRADER: 'Individual Business / Sole Trader',
  ORGANISATION: 'Registered Company / Partnership / Organisation',
}

export const DOC_TYPE_LABEL: Record<string, string> = {
  REGISTRATION_CERTIFICATE: 'Registration certificate',
  EXEMPTION_EVIDENCE: 'Registration exemption evidence',
  LICENCE: 'Licence',
  AUTHORITY_LETTER: 'Letter of authority',
  OWNERSHIP: 'Ownership information',
  ADDRESS: 'Business address evidence',
  OTHER: 'Other',
}

export function sellerErrorMessage(error: unknown, fallback: string): string {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown } } })?.response
  if (response?.status === 401) return 'Your session has expired. Please sign in again.'
  const detail = response?.data?.detail
  if (typeof detail === 'string' && detail.length > 0 && detail.length < 300) return detail
  if (detail && typeof detail === 'object' && typeof (detail as { message?: unknown }).message === 'string') {
    return (detail as { message: string }).message
  }
  return fallback
}
