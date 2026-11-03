'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Archive, Download, ImagePlus, Loader2, Package, RefreshCw, ShieldCheck, Store, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/hooks/use-auth'
import { SellerRegistration } from '@/components/dashboard/seller-registration'
import {
  CONDITION_LABEL,
  Category,
  ItemCondition,
  KIND_LABEL,
  LISTING_STATUS_LABEL,
  Listing,
  ListingInput,
  ListingKind,
  MarketOrder,
  MarketStatus,
  SellerSummary,
  SortOrder,
  acceptOrder,
  archiveListing,
  browseListings,
  categoryLabel,
  deleteListingImage,
  downloadOrder,
  getCategories,
  getMarketStatus,
  imageSrc,
  marketErrorMessage,
  myListings,
  myOrders,
  newCheckoutReference,
  openOrderRequest,
  orderAction,
  ownImageUrl,
  payOrder,
  placeOrder,
  saveListing,
  sellerSummary,
  setListingPublished,
  uploadListingFile,
  uploadListingImage,
  withdrawOrderRequest,
} from '@/lib/marketplace'

type Tab = 'browse' | 'purchases' | 'sales' | 'listings' | 'seller'

export const ACCEPTANCE_TEXT =
  'I confirm that I have received the product or the completed service as described, and I accept it. ' +
  'My confirmation is final: it lets the seller hand over and starts the payment to the seller.'

const STATUS_LABEL: Record<string, string> = {
  UNPAID: 'Awaiting payment', AWAITING_FULFILMENT: 'Paid, awaiting handover', AWAITING_ACCEPTANCE: 'Awaiting your confirmation',
  ACCEPTED: 'Accepted', CANCELLED: 'Cancelled', REFUND_PENDING: 'Refund in progress', REFUNDED: 'Refunded',
  NOT_STARTED: 'Not started', SETTLEMENT_PENDING: 'Payment to seller requested', SETTLEMENT_RETRY_NEEDED: 'Payment to seller delayed (retrying)',
  SETTLED: 'Seller paid',
}

function Disclosure({ d }: { d: { warranty: string; insurance: string; consumer_rights: string } }) {
  return (
    <div className="space-y-1 rounded-md bg-gray-50 p-3 text-xs text-gray-700 dark:bg-gray-800/60 dark:text-gray-300">
      <p><span className="font-semibold">Warranty:</span> {d.warranty}</p>
      <p><span className="font-semibold">Insurance:</span> {d.insurance}</p>
      <p className="text-gray-500 dark:text-gray-400">{d.consumer_rights}</p>
    </div>
  )
}

function Notice({ text, tone = 'info' }: { text: string; tone?: 'info' | 'error' }) {
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`flex items-start gap-2 rounded-md p-3 text-sm ${tone === 'error'
      ? 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300' : 'bg-amber-50 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200'}`}>
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> <span>{text}</span>
    </div>
  )
}

function useCategories(): Category[] {
  const [categories, setCategories] = useState<Category[]>([])
  useEffect(() => {
    getCategories().then((c) => setCategories(Array.isArray(c) ? c.filter((x) => typeof x?.code === 'string') : []))
      .catch(() => setCategories([]))
  }, [])
  return categories
}

function BrowseTab({ status, onOrdered }: { status: MarketStatus; onOrdered: () => void }) {
  const [kind, setKind] = useState<ListingKind | ''>('')
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [sort, setSort] = useState<SortOrder>('newest')
  const [items, setItems] = useState<Listing[] | null>(null)
  const [open, setOpen] = useState<Listing | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const categories = useCategories()
  // One checkout reference per opened listing: a double click or a retry returns the same order.
  const checkoutRef = useRef<string>('')

  const load = useCallback(async () => {
    setError('')
    try { setItems(await browseListings({ kind: kind || undefined, q: q.trim() || undefined, category: category || undefined, sort })) }
    catch (e) { setError(marketErrorMessage(e, 'Listings could not be loaded.')); setItems([]) }
  }, [kind, q, category, sort])
  useEffect(() => { load() }, [load])
  const show = (listing: Listing) => { checkoutRef.current = newCheckoutReference(); setOpen(listing) }

  const buy = async (listing: Listing) => {
    setBusy(true); setError('')
    try {
      const order = await placeOrder(listing.id, checkoutRef.current || undefined)
      const paid = await payOrder(order.id)
      if (paid.payment?.payment_url) window.location.href = paid.payment.payment_url
      onOrdered()
    } catch (e) { setError(marketErrorMessage(e, 'The order could not be placed.')) }
    finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input placeholder="Search listings" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search listings" />
        <select className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={kind} aria-label="Kind"
                onChange={(e) => setKind(e.target.value as ListingKind | '')}>
          <option value="">All kinds</option>
          {(Object.keys(KIND_LABEL) as ListingKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
        </select>
        <select className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={category} aria-label="Category"
                onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>
          {categories.map((c) => <option key={c.code} value={c.code}>{categoryLabel(c.code)}</option>)}
        </select>
        <select className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={sort} aria-label="Sort"
                onChange={(e) => setSort(e.target.value as SortOrder)}>
          <option value="newest">Newest</option>
          <option value="price_asc">Price: low to high</option>
          <option value="price_desc">Price: high to low</option>
        </select>
      </div>
      {error && <Notice text={error} tone="error" />}
      {items === null ? <Loader2 className="h-5 w-5 animate-spin" /> : items.length === 0 ? (
        <p className="text-sm text-gray-500">No listings yet.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((l) => (
            <Card key={l.id} className="flex flex-col gap-2 p-4">
              {l.images?.[0] && (
                <img src={imageSrc(l.images[0].url)} alt="" loading="lazy" className="h-40 w-full rounded-md object-cover" />
              )}
              <span className="text-xs font-medium uppercase text-gray-500">
                {KIND_LABEL[l.kind]}{l.category ? ` · ${categoryLabel(l.category)}` : ''}
              </span>
              <h3 className="font-semibold">{l.title}</h3>
              <p className="line-clamp-3 text-sm text-gray-600 dark:text-gray-300">{l.description}</p>
              <p className="mt-auto text-lg font-bold">${l.buyer_price_usd}</p>
              <Button variant="outline" onClick={() => show(l)}>View details</Button>
            </Card>
          ))}
        </div>
      )}
      {open && (
        <Card className="space-y-3 p-4" aria-label="Listing details">
          <div className="flex items-start justify-between gap-2">
            <div>
              <span className="text-xs font-medium uppercase text-gray-500">{KIND_LABEL[open.kind]}</span>
              <h3 className="text-lg font-semibold">{open.title}</h3>
            </div>
            <Button variant="ghost" onClick={() => setOpen(null)}>Close</Button>
          </div>
          {(open.images?.length ?? 0) > 0 && (
            <div className="flex gap-2 overflow-x-auto">
              {open.images.map((img) => (
                <img key={img.id} src={imageSrc(img.url)} alt="" className="h-32 w-32 flex-shrink-0 rounded-md object-cover" />
              ))}
            </div>
          )}
          {open.item_condition && <p className="text-sm"><span className="font-semibold">Condition:</span> {CONDITION_LABEL[open.item_condition]}</p>}
          <p className="whitespace-pre-line text-sm">{open.description}</p>
          {open.handover_details && <p className="text-sm"><span className="font-semibold">Handover:</span> {open.handover_details}</p>}
          {open.kind === 'PHYSICAL' && open.quantity_available !== null && <p className="text-sm">{open.quantity_available} available</p>}
          <Disclosure d={open.disclosures} />
          <p className="text-xl font-bold">${open.buyer_price_usd}</p>
          {!status.checkout_available ? (
            <Notice text="Checkout is not available yet: payments will open once a payment custodian is in place." />
          ) : (
            <Button disabled={busy || !open.available} onClick={() => buy(open)}>
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Buy for ${open.buyer_price_usd}
            </Button>
          )}
        </Card>
      )}
    </div>
  )
}

function OrderCard({ order, role, policy, onChange }: { order: MarketOrder; role: 'buyer' | 'seller'; policy: string; onChange: () => void }) {
  const [ack, setAck] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError('')
    try { await fn(); onChange() } catch (e) { setError(marketErrorMessage(e, 'The request could not be completed.')) }
    finally { setBusy(false) }
  }
  const [asking, setAsking] = useState(false)
  const [kind, setKind] = useState<'CANCELLATION' | 'REFUND'>('REFUND')
  const [reason, setReason] = useState('')
  const canAccept = role === 'buyer' && order.acceptance_status !== 'ACCEPTED'
    && ['AWAITING_FULFILMENT', 'AWAITING_ACCEPTANCE'].includes(order.fulfilment_status)
  const request = order.open_request
  return (
    <Card className="space-y-2 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">{order.listing?.title || `Order #${order.id}`}</h3>
        <span className="text-sm font-bold">${(role === 'buyer' ? order.buyer_total_amount : order.seller_base_amount).toFixed(2)}</span>
      </div>
      <dl className="grid grid-cols-1 gap-1 text-sm sm:grid-cols-3">
        <div><dt className="text-xs text-gray-500">Order</dt><dd>{STATUS_LABEL[order.fulfilment_status] || order.fulfilment_status}</dd></div>
        <div><dt className="text-xs text-gray-500">Buyer confirmation</dt>
          <dd>{order.acceptance_status === 'ACCEPTED' ? `Accepted (${order.acceptance_reference})` : 'Not yet'}</dd></div>
        <div><dt className="text-xs text-gray-500">Settlement</dt><dd>{STATUS_LABEL[order.settlement_status] || order.settlement_status}</dd></div>
      </dl>
      {role === 'seller' && (
        <p className={`flex items-center gap-2 rounded-md p-2 text-sm font-medium ${order.acceptance_status === 'ACCEPTED'
          ? 'bg-green-50 text-green-800 dark:bg-green-900/30 dark:text-green-200' : 'bg-amber-50 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200'}`}>
          <ShieldCheck className="h-4 w-4" aria-hidden /> {order.handover_instruction}
        </p>
      )}
      {order.listing && <Disclosure d={order.listing} />}
      {request && (
        <Notice text={role === 'buyer'
          ? `Your ${request.kind.toLowerCase()} request is with MyHigh5 support.`
          : `The buyer asked MyHigh5 support for a ${request.kind.toLowerCase()}. Do not hand over until support has reviewed it.`} />
      )}
      {error && <Notice text={error} tone="error" />}
      <div className="flex flex-wrap gap-2">
        {role === 'buyer' && order.can_download && (
          <Button size="sm" disabled={busy} onClick={() => run(() => downloadOrder(order.id, 'download'))}>
            <Download className="mr-1 h-4 w-4" /> Download
          </Button>
        )}
        {role === 'buyer' && order.fulfilment_status === 'UNPAID' && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => orderAction(order.id, 'cancel'))}>Cancel order</Button>
        )}
        {role === 'seller' && order.fulfilment_status === 'AWAITING_FULFILMENT' && !order.digital && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => orderAction(order.id, 'fulfill'))}>Mark as delivered</Button>
        )}
        {role === 'seller' && order.acceptance_status === 'ACCEPTED' && !order.seller_verified_at && (
          <Button size="sm" disabled={busy} onClick={() => run(() => orderAction(order.id, 'verify'))}>I have checked the buyer&apos;s confirmation</Button>
        )}
        {canAccept && !request && !asking && (
          <Button size="sm" variant="outline" disabled={busy} onClick={() => setAsking(true)}>Ask support to cancel or refund</Button>
        )}
        {role === 'buyer' && request && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => run(() => withdrawOrderRequest(order.id))}>Withdraw my request</Button>
        )}
      </div>
      {asking && (
        <div className="space-y-2 border-t pt-2" aria-label="Support request">
          <p className="text-xs text-gray-500">MyHigh5 support reviews every request. Nothing is refunded automatically.</p>
          <select className="h-9 rounded-md border border-input bg-background px-2 text-sm" aria-label="Request type" value={kind}
                  onChange={(e) => setKind(e.target.value as 'CANCELLATION' | 'REFUND')}>
            <option value="REFUND">Refund</option>
            <option value="CANCELLATION">Cancellation</option>
          </select>
          <Textarea rows={3} aria-label="What happened" placeholder="What happened? (at least 10 characters)" value={reason}
                    onChange={(e) => setReason(e.target.value)} />
          <div className="flex gap-2">
            <Button size="sm" disabled={busy || reason.trim().length < 10}
                    onClick={() => run(async () => { await openOrderRequest(order.id, kind, reason.trim()); setAsking(false); setReason('') })}>
              Send to support
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAsking(false)}>Cancel</Button>
          </div>
        </div>
      )}
      {canAccept && !order.digital && (
        <div className="space-y-2 border-t pt-2">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            <span>{ACCEPTANCE_TEXT}</span>
          </label>
          <Button size="sm" disabled={!ack || busy} onClick={() => run(() => acceptOrder(order.id, policy))}>Confirm and accept</Button>
        </div>
      )}
      {role === 'buyer' && order.digital && order.can_download && !order.digital_delivered_at && (
        <p className="text-xs text-gray-500">Your purchase is final once the file has been downloaded completely.</p>
      )}
    </Card>
  )
}

const EMPTY: ListingInput = {
  kind: 'PHYSICAL', title: '', description: '', price_usd: '', quantity_available: null, handover_details: '',
  warranty_available: false, warranty_terms: '', insurance_available: false, insurance_terms: '',
  category: null, item_condition: null,
}

function OwnImage({ url }: { url: string }) {
  const [src, setSrc] = useState('')
  useEffect(() => {
    let revoke = ''
    ownImageUrl(url).then((u) => { revoke = u; setSrc(u) }).catch(() => setSrc(''))
    return () => { if (revoke) URL.revokeObjectURL(revoke) }
  }, [url])
  return src ? <img src={src} alt="" className="h-20 w-20 rounded-md object-cover" /> : <div className="h-20 w-20 rounded-md bg-gray-100 dark:bg-gray-800" />
}

function ListingImages({ listing, onChange }: { listing: Listing; onChange: (l: Listing) => void }) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const run = async (fn: () => Promise<Listing>) => {
    setBusy(true); setError('')
    try { onChange(await fn()) } catch (e) { setError(marketErrorMessage(e, 'The photo could not be saved.')) }
    finally { setBusy(false) }
  }
  return (
    <div className="space-y-2" aria-label="Photos">
      <Label>Photos (JPEG, PNG or WebP, up to 5 MB, 8 at most)</Label>
      <div className="flex flex-wrap gap-2">
        {(listing.images || []).map((img) => (
          <div key={img.id} className="relative">
            <OwnImage url={img.url} />
            <button type="button" aria-label="Remove photo" disabled={busy}
                    className="absolute right-1 top-1 rounded bg-white/90 p-1 text-red-600 dark:bg-gray-900/90"
                    onClick={() => run(() => deleteListingImage(listing.id, img.id))}>
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        ))}
        {(listing.images || []).length < 8 && (
          <label className="flex h-20 w-20 cursor-pointer items-center justify-center rounded-md border border-dashed text-gray-500">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <ImagePlus className="h-5 w-5" aria-hidden />}
            <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="Add photo" disabled={busy}
                   onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) run(() => uploadListingImage(listing.id, f)) }} />
          </label>
        )}
      </div>
      {error && <Notice text={error} tone="error" />}
    </div>
  )
}

function ListingForm({ initial, onSaved, onCancel }: { initial?: Listing; onSaved: () => void; onCancel: () => void }) {
  const [form, setForm] = useState<ListingInput>(initial ? {
    kind: initial.kind, title: initial.title, description: initial.description, price_usd: initial.seller_price_usd || '',
    quantity_available: initial.quantity_available, handover_details: initial.handover_details || '',
    warranty_available: initial.warranty_available, warranty_terms: initial.warranty_terms || '',
    insurance_available: initial.insurance_available, insurance_terms: initial.insurance_terms || '',
    category: initial.category, item_condition: initial.item_condition,
  } : EMPTY)
  const [current, setCurrent] = useState<Listing | undefined>(initial)
  const categories = useCategories()
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof ListingInput>(key: K, value: ListingInput[K]) => setForm((f) => ({ ...f, [key]: value }))

  const submit = async () => {
    setBusy(true); setError('')
    try {
      const saved = await saveListing({
        ...form,
        quantity_available: form.kind === 'PHYSICAL' ? form.quantity_available : null,
        item_condition: form.kind === 'PHYSICAL' ? form.item_condition : null,
        category: form.category || null,
        handover_details: form.handover_details || null,
        warranty_terms: form.warranty_available ? form.warranty_terms : null,
        insurance_terms: form.insurance_available ? form.insurance_terms : null,
      }, initial?.id)
      if (file && saved.kind === 'DIGITAL') await uploadListingFile(saved.id, file)
      onSaved()
    } catch (e) { setError(marketErrorMessage(e, 'The listing could not be saved.')) }
    finally { setBusy(false) }
  }

  return (
    <Card className="space-y-3 p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div><Label htmlFor="ml-kind">Kind</Label>
          <select id="ml-kind" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={form.kind}
                  disabled={!!initial && initial.status !== 'DRAFT'} onChange={(e) => set('kind', e.target.value as ListingKind)}>
            {(Object.keys(KIND_LABEL) as ListingKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select></div>
        <div><Label htmlFor="ml-price">Your price (USD)</Label>
          <Input id="ml-price" inputMode="decimal" value={form.price_usd} onChange={(e) => set('price_usd', e.target.value)} />
          <p className="mt-1 text-xs text-gray-500">Buyers pay your price plus the 20% marketplace fee.</p></div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div><Label htmlFor="ml-cat">Category</Label>
          <select id="ml-cat" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={form.category || ''}
                  onChange={(e) => set('category', e.target.value || null)}>
            <option value="">Choose a category</option>
            {categories.map((c) => <option key={c.code} value={c.code}>{categoryLabel(c.code)}{c.regulated ? ' (reviewed sellers only)' : ''}</option>)}
          </select></div>
        {form.kind === 'PHYSICAL' && (
          <div><Label htmlFor="ml-cond">Condition</Label>
            <select id="ml-cond" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={form.item_condition || ''}
                    onChange={(e) => set('item_condition', (e.target.value || null) as ItemCondition | null)}>
              <option value="">Not stated</option>
              {(Object.keys(CONDITION_LABEL) as ItemCondition[]).map((c) => <option key={c} value={c}>{CONDITION_LABEL[c]}</option>)}
            </select></div>
        )}
      </div>
      <div><Label htmlFor="ml-title">Title</Label><Input id="ml-title" value={form.title} onChange={(e) => set('title', e.target.value)} /></div>
      <div><Label htmlFor="ml-desc">Description</Label><Textarea id="ml-desc" rows={4} value={form.description} onChange={(e) => set('description', e.target.value)} /></div>
      {form.kind === 'PHYSICAL' && (
        <div><Label htmlFor="ml-qty">Units available (leave empty if not tracked)</Label>
          <Input id="ml-qty" inputMode="numeric" value={form.quantity_available ?? ''}
                 onChange={(e) => set('quantity_available', e.target.value === '' ? null : Number.parseInt(e.target.value, 10))} /></div>
      )}
      {form.kind !== 'DIGITAL' ? (
        <div><Label htmlFor="ml-hand">How it is handed over</Label>
          <Textarea id="ml-hand" rows={2} value={form.handover_details || ''} onChange={(e) => set('handover_details', e.target.value)} /></div>
      ) : (
        <div><Label htmlFor="ml-file">File (PDF, EPUB or ZIP, up to 50 MB)</Label>
          <Input id="ml-file" type="file" accept=".pdf,.epub,.zip" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          {initial?.file_name && <p className="mt-1 text-xs text-gray-500">Current file: {initial.file_name}</p>}</div>
      )}
      {(['warranty', 'insurance'] as const).map((k) => (
        <div key={k} className="space-y-1">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form[`${k}_available`]} onChange={(e) => set(`${k}_available`, e.target.checked)} />
            {k === 'warranty' ? 'I offer a warranty' : 'Insurance is included'}
          </label>
          {form[`${k}_available`] && (
            <Textarea rows={2} aria-label={`${k} terms`} placeholder={`Describe the ${k} (what is covered, for how long, by whom)`}
                      value={form[`${k}_terms`] || ''} onChange={(e) => set(`${k}_terms`, e.target.value)} />
          )}
        </div>
      ))}
      {current ? <ListingImages listing={current} onChange={setCurrent} />
        : <p className="text-xs text-gray-500">Save the draft first, then add photos.</p>}
      {error && <Notice text={error} tone="error" />}
      <div className="flex gap-2">
        <Button disabled={busy} onClick={submit}>{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save draft</Button>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </Card>
  )
}

function ListingsTab() {
  const [items, setItems] = useState<Listing[] | null>(null)
  const [editing, setEditing] = useState<Listing | 'new' | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    try { setItems(await myListings()) } catch (e) { setError(marketErrorMessage(e, 'Your listings could not be loaded.')); setItems([]) }
  }, [])
  useEffect(() => { load() }, [load])
  const toggle = async (l: Listing) => {
    setError('')
    try { await setListingPublished(l.id, l.status !== 'PUBLISHED'); load() }
    catch (e) { setError(marketErrorMessage(e, 'The listing could not be updated.')) }
  }
  const archive = async (l: Listing) => {
    setError('')
    try { await archiveListing(l.id); load() }
    catch (e) { setError(marketErrorMessage(e, 'The listing could not be archived.')) }
  }
  if (editing) return <ListingForm initial={editing === 'new' ? undefined : editing} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />
  return (
    <div className="space-y-3">
      <Button onClick={() => setEditing('new')}><Package className="mr-2 h-4 w-4" />New listing</Button>
      {error && <Notice text={error} tone="error" />}
      {items === null ? <Loader2 className="h-5 w-5 animate-spin" /> : items.length === 0 ? <p className="text-sm text-gray-500">You have no listings.</p> : items.map((l) => (
        <Card key={l.id} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <p className="font-semibold">{l.title}</p>
            <p className="text-xs text-gray-500">
              {KIND_LABEL[l.kind]} · {categoryLabel(l.category)} · {l.status ? LISTING_STATUS_LABEL[l.status] : ''} · your price ${l.seller_price_usd} · buyers pay ${l.buyer_price_usd}
            </p>
            {l.status === 'SUSPENDED' && l.moderation_note && <Notice text={`MyHigh5: ${l.moderation_note}`} />}
          </div>
          {l.status !== 'SUSPENDED' && l.status !== 'ARCHIVED' && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => setEditing(l)}>Edit</Button>
              <Button size="sm" onClick={() => toggle(l)}>{l.status === 'PUBLISHED' ? 'Unpublish' : 'Publish'}</Button>
              <Button size="sm" variant="ghost" onClick={() => archive(l)}><Archive className="mr-1 h-4 w-4" />Archive</Button>
            </div>
          )}
        </Card>
      ))}
    </div>
  )
}

function SalesSummary() {
  const [summary, setSummary] = useState<SellerSummary | null>(null)
  useEffect(() => { sellerSummary().then(setSummary).catch(() => setSummary(null)) }, [])
  if (!summary || typeof summary.held_by_custodian_usd !== 'string') return null
  return (
    <Card className="space-y-1 p-4" aria-label="Sales summary">
      <div className="flex flex-wrap gap-6 text-sm">
        <div><p className="text-xs text-gray-500">Held by the payment custodian</p><p className="font-semibold">${summary.held_by_custodian_usd}</p></div>
        <div><p className="text-xs text-gray-500">Paid to you by the custodian</p><p className="font-semibold">${summary.paid_by_custodian_usd}</p></div>
      </div>
      <p className="text-xs text-gray-500">{summary.note}</p>
    </Card>
  )
}

export function MarketplaceDashboard() {
  const { user } = useAuth()
  const [status, setStatus] = useState<MarketStatus | null>(null)
  const [tab, setTab] = useState<Tab>('browse')
  const [orders, setOrders] = useState<MarketOrder[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getMarketStatus().then(setStatus).catch(() => setStatus({ enabled: false, checkout_available: false, acceptance_policy_version: '' }))
  }, [])
  const loadOrders = useCallback(async () => {
    setError('')
    try { setOrders(await myOrders()) } catch (e) { setError(marketErrorMessage(e, 'Orders could not be loaded.')); setOrders([]) }
  }, [])
  useEffect(() => { if (status?.enabled && (tab === 'purchases' || tab === 'sales')) loadOrders() }, [status, tab, loadOrders])

  if (!status) return <Loader2 className="m-6 h-6 w-6 animate-spin" />
  if (!status.enabled) {
    return (
      <div className="mx-auto max-w-3xl p-4">
        <Card className="space-y-2 p-6 text-center">
          <Store className="mx-auto h-8 w-8 text-gray-400" aria-hidden />
          <h1 className="text-xl font-semibold">Marketplace</h1>
          <p className="text-sm text-gray-600 dark:text-gray-300">The marketplace is not open yet.</p>
        </Card>
      </div>
    )
  }
  const mine = (orders || []).filter((o) => (tab === 'purchases' ? o.buyer_user_id : o.seller_user_id) === user?.id)
  const tabs: [Tab, string][] = [['browse', 'Browse'], ['purchases', 'My purchases'], ['sales', 'My sales'], ['listings', 'My listings'],
    ['seller', 'Seller registration']]
  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4">
      <h1 className="flex items-center gap-2 text-2xl font-semibold"><Store className="h-6 w-6" aria-hidden /> Marketplace</h1>
      <div role="tablist" className="flex gap-1 overflow-x-auto border-b">
        {tabs.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
                  className={`whitespace-nowrap px-3 py-2 text-sm font-medium ${tab === key ? 'border-b-2 border-primary text-primary' : 'text-gray-500'}`}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'browse' && <BrowseTab status={status} onOrdered={() => setTab('purchases')} />}
      {tab === 'listings' && <ListingsTab />}
      {tab === 'seller' && <SellerRegistration />}
      {(tab === 'purchases' || tab === 'sales') && (
        <div className="space-y-3">
          {tab === 'sales' && <SalesSummary />}
          <Button size="sm" variant="ghost" onClick={loadOrders}><RefreshCw className="mr-1 h-4 w-4" />Refresh</Button>
          {error && <Notice text={error} tone="error" />}
          {orders === null ? <Loader2 className="h-5 w-5 animate-spin" /> : mine.length === 0 ? <p className="text-sm text-gray-500">No orders.</p>
            : mine.map((o) => <OrderCard key={o.id} order={o} role={tab === 'purchases' ? 'buyer' : 'seller'}
                                         policy={status.acceptance_policy_version} onChange={loadOrders} />)}
        </div>
      )}
    </div>
  )
}
