import api from '@/lib/api'
import { getEffectiveApiUrl } from '@/lib/config'

export type ListingKind = 'PHYSICAL' | 'SERVICE' | 'DIGITAL'

export type Disclosures = { warranty: string; insurance: string; consumer_rights: string }

export type ListingStatus = 'DRAFT' | 'PUBLISHED' | 'UNPUBLISHED' | 'SUSPENDED' | 'ARCHIVED'
export type ItemCondition = 'NEW' | 'USED' | 'REFURBISHED'
export type ListingImage = { id: number; url: string; width: number; height: number }
export type Category = { code: string; regulated: boolean }
export type SortOrder = 'newest' | 'price_asc' | 'price_desc'

/** A listing as the API returns it; the owner fields are present only on the seller's own listings. */
export type Listing = {
  id: number
  kind: ListingKind
  title: string
  description: string
  seller_user_id: number
  buyer_price_usd: string
  quantity_available: number | null
  available: boolean
  handover_details: string | null
  warranty_available: boolean
  insurance_available: boolean
  disclosures: Disclosures
  has_file: boolean
  published_at: string | null
  category: string | null
  item_condition: ItemCondition | null
  images: ListingImage[]
  status?: ListingStatus
  moderation_note?: string | null
  seller_price_usd?: string
  markup_usd?: string
  warranty_terms?: string | null
  insurance_terms?: string | null
  file_name?: string | null
  file_size?: number | null
}

export type ListingInput = {
  kind: ListingKind
  title: string
  description: string
  price_usd: string
  quantity_available: number | null
  handover_details: string | null
  warranty_available: boolean
  warranty_terms: string | null
  insurance_available: boolean
  insurance_terms: string | null
  category: string | null
  item_condition: ItemCondition | null
}

export type OrderRequest = {
  id: number
  order_id: number
  kind: 'CANCELLATION' | 'REFUND'
  reason: string
  status: 'OPEN' | 'RESOLVED'
  resolution: 'REFUNDED' | 'DECLINED' | 'WITHDRAWN' | null
  resolution_note: string | null
  created_at: string | null
  resolved_at: string | null
}

export type SellerSummary = {
  orders_by_state: Record<string, number>
  held_by_custodian_usd: string
  paid_by_custodian_usd: string
  custodian: string
  note: string
}

export type MarketOrder = {
  id: number
  state: string
  item_type: string
  buyer_user_id: number
  seller_user_id: number
  buyer_total_amount: number
  seller_base_amount: number
  created_at: string | null
  listing: (Disclosures & { title: string; kind: ListingKind; handover_details: string | null }) | null
  digital: boolean
  digital_delivered_at: string | null
  can_download: boolean
  acceptance_status: 'ACCEPTED' | 'NOT_ACCEPTED'
  acceptance_reference: string | null
  accepted_at: string | null
  seller_verified_at: string | null
  handover_instruction: string
  fulfilment_status: string
  settlement_status: string
  open_request?: OrderRequest | null
}

export type MarketStatus = { enabled: boolean; checkout_available: boolean; acceptance_policy_version: string }

const M = '/api/v1/marketplace'

export async function getMarketStatus(): Promise<MarketStatus> {
  return (await api.get<MarketStatus>(`${M}/status`)).data
}

export async function browseListings(params: { kind?: ListingKind; q?: string; category?: string; sort?: SortOrder; page?: number } = {}): Promise<Listing[]> {
  return (await api.get<Listing[]>(`${M}/listings`, { params })).data
}

export async function getCategories(): Promise<Category[]> {
  return (await api.get<Category[]>(`${M}/categories`)).data
}

export async function archiveListing(id: number): Promise<Listing> {
  return (await api.post<Listing>(`${M}/listings/${id}/archive`)).data
}

export async function uploadListingImage(id: number, file: File): Promise<Listing> {
  const form = new FormData()
  form.append('file', file)
  return (await api.post<Listing>(`${M}/listings/${id}/images`, form, { headers: { 'Content-Type': 'multipart/form-data' } })).data
}

export async function deleteListingImage(id: number, imageId: number): Promise<Listing> {
  return (await api.delete<Listing>(`${M}/listings/${id}/images/${imageId}`)).data
}

export async function sellerSummary(): Promise<SellerSummary> {
  return (await api.get<SellerSummary>(`${M}/seller/summary`)).data
}

export async function openOrderRequest(id: number, kind: 'CANCELLATION' | 'REFUND', reason: string): Promise<MarketOrder> {
  return (await api.post<MarketOrder>(`${M}/orders/${id}/requests`, { kind, reason })).data
}

export async function withdrawOrderRequest(id: number): Promise<MarketOrder> {
  return (await api.post<MarketOrder>(`${M}/orders/${id}/requests/withdraw`)).data
}

/** Public listing photos are served by the API; a relative URL is resolved against the API host. */
export function imageSrc(url: string): string {
  const base = getEffectiveApiUrl().replace(/\/+$/, '')
  return url.startsWith('http') ? url : `${base}${url}`
}

/** The seller's own photos need the sign-in token, so they are fetched and shown from a local object URL. */
export async function ownImageUrl(url: string): Promise<string> {
  const response = await api.get(url, { responseType: 'blob' })
  return URL.createObjectURL(response.data as Blob)
}

/** A checkout reference: a repeated click or retry returns the same order instead of a second one. */
export function newCheckoutReference(): string {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`
  return `chk-${random}`.replace(/[^A-Za-z0-9_-]/g, '').slice(0, 64)
}

export async function myListings(): Promise<Listing[]> {
  return (await api.get<Listing[]>(`${M}/my-listings`)).data
}

export async function saveListing(input: ListingInput, id?: number): Promise<Listing> {
  return id ? (await api.patch<Listing>(`${M}/listings/${id}`, input)).data
    : (await api.post<Listing>(`${M}/listings`, input)).data
}

export async function setListingPublished(id: number, publish: boolean): Promise<Listing> {
  return (await api.post<Listing>(`${M}/listings/${id}/${publish ? 'publish' : 'unpublish'}`)).data
}

export async function uploadListingFile(id: number, file: File): Promise<Listing> {
  const form = new FormData()
  form.append('file', file)
  return (await api.put<Listing>(`${M}/listings/${id}/file`, form, { headers: { 'Content-Type': 'multipart/form-data' } })).data
}

export async function myOrders(): Promise<MarketOrder[]> {
  return (await api.get<MarketOrder[]>(`${M}/orders`)).data
}

export async function placeOrder(listingId: number, clientReference?: string): Promise<MarketOrder> {
  return (await api.post<MarketOrder>(`${M}/orders`, { item_type: 'listing', item_id: listingId, client_reference: clientReference })).data
}

export async function payOrder(id: number): Promise<MarketOrder & { payment?: { payment_url?: string } }> {
  return (await api.post(`${M}/orders/${id}/pay`)).data
}

export async function acceptOrder(id: number, policyVersion: string): Promise<MarketOrder> {
  return (await api.post<MarketOrder>(`${M}/orders/${id}/accept`, { policy_version: policyVersion, acknowledge: true })).data
}

export async function orderAction(id: number, action: 'fulfill' | 'verify' | 'cancel'): Promise<MarketOrder> {
  return (await api.post<MarketOrder>(`${M}/orders/${id}/${action}`)).data
}

/** Downloads a paid digital order. The purchase is finalised by the server once the whole file was sent. */
export async function downloadOrder(id: number, fallbackName: string): Promise<void> {
  const response = await api.get(`${M}/orders/${id}/download`, { responseType: 'blob' })
  const disposition: string = response.headers?.['content-disposition'] || ''
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] || fallbackName
  const url = URL.createObjectURL(response.data as Blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

export function marketErrorMessage(error: unknown, fallback: string): string {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown } } })?.response
  if (response?.status === 401) return 'Your session has expired. Please sign in again.'
  const detail = response?.data?.detail
  if (typeof detail === 'string' && detail.length > 0 && detail.length < 300) return detail
  // e.g. SELLER_NOT_APPROVED: { code, message }
  if (detail && typeof detail === 'object' && typeof (detail as { message?: unknown }).message === 'string') {
    return (detail as { message: string }).message
  }
  return fallback
}

export const KIND_LABEL: Record<ListingKind, string> = { PHYSICAL: 'Physical product', SERVICE: 'Service', DIGITAL: 'E-book / digital' }

export const CONDITION_LABEL: Record<ItemCondition, string> = { NEW: 'New', USED: 'Used', REFURBISHED: 'Refurbished' }

export const LISTING_STATUS_LABEL: Record<ListingStatus, string> = {
  DRAFT: 'Draft', PUBLISHED: 'Published', UNPUBLISHED: 'Unpublished', SUSPENDED: 'Suspended by MyHigh5', ARCHIVED: 'Archived',
}

export function categoryLabel(code: string | null | undefined): string {
  if (!code) return 'Uncategorised'
  return code.toLowerCase().split('_').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}
