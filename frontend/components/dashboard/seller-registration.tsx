'use client'

import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, BadgeCheck, Briefcase, Loader2, Upload, User } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  CATEGORY_LABEL,
  DOC_TYPE_LABEL,
  SELLER_STATUS_LABEL,
  SellerApplicationInput,
  SellerCategory,
  SellerStatus,
  appealSellerDecision,
  getSellerStatus,
  saveSellerApplication,
  sellerErrorMessage,
  submitSellerApplication,
  uploadSellerDocument,
} from '@/lib/seller-verification'

export const APPROVAL_MEANING =
  'MyHigh5 seller approval means you may sell on MyHigh5. It is not a government business registration, ' +
  'tax registration or licence, and it is not proof of full legal compliance.'

const INDICATORS: [string, string][] = [
  ['sells_new_stock', 'I regularly sell new items (not my own used belongings)'],
  ['buys_for_resale', 'I buy goods in order to resell them'],
  ['manufactures_for_sale', 'I make or manufacture goods to sell'],
  ['regular_paid_services', 'I regularly offer paid services'],
  ['regular_digital_products', 'I regularly sell digital products'],
]

const EDITABLE = ['DRAFT', 'ACTION_REQUIRED']

function fromApplication(status: SellerStatus): SellerApplicationInput | null {
  const a = status.application
  if (!a || !EDITABLE.includes(a.status)) return null
  return {
    seller_category: a.seller_category, business_structure: a.business_structure, legal_name: a.legal_name,
    trading_name: a.trading_name, residence_country: a.residence_country, establishment_country: a.establishment_country,
    establishment_subdivision: a.establishment_subdivision, customer_markets: a.customer_markets || [],
    business_address: a.business_address, contact_phone: a.contact_phone, product_categories: a.product_categories || [],
    products_description: a.products_description, commercial_indicators: a.commercial_indicators || {},
    registration_authority: a.registration_authority, registration_number: a.registration_number,
    exemption_basis: a.exemption_basis, tax_registered: a.tax_registered, licences: a.licences || [],
    representative: a.representative || null, ownership: a.ownership || [],
  }
}

function Field({ id, label, value, onChange, hint, multiline }: {
  id: string; label: string; value: string | null | undefined; onChange: (v: string) => void; hint?: string; multiline?: boolean
}) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      {multiline ? <Textarea id={id} rows={2} value={value || ''} onChange={(e) => onChange(e.target.value)} />
        : <Input id={id} value={value || ''} onChange={(e) => onChange(e.target.value)} />}
      {hint && <p className="mt-1 text-xs text-gray-500">{hint}</p>}
    </div>
  )
}

function ApplicationForm({ status, initial, onChange }: {
  status: SellerStatus; initial: SellerApplicationInput; onChange: (s: SellerStatus) => void
}) {
  const [form, setForm] = useState<SellerApplicationInput>(initial)
  const [taxId, setTaxId] = useState('')
  const [declared, setDeclared] = useState(false)
  const [docType, setDocType] = useState('REGISTRATION_CERTIFICATE')
  const [docFile, setDocFile] = useState<File | null>(null)
  const [docExpiry, setDocExpiry] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = <K extends keyof SellerApplicationInput>(key: K, value: SellerApplicationInput[K]) =>
    setForm((f) => ({ ...f, [key]: value }))
  const business = form.seller_category !== 'PRIVATE'
  const exempt = form.seller_category === 'SOLE_TRADER' && form.business_structure === 'EXEMPT'
  const app = status.application

  const payload = (): SellerApplicationInput => ({
    ...form,
    residence_country: (form.residence_country || '').toUpperCase() || null,
    establishment_country: (form.establishment_country || '').toUpperCase() || null,
    ...(taxId.trim() ? { tax_identifier: taxId.trim() } : {}),
  })

  const run = async (fn: () => Promise<SellerStatus>, fallback: string) => {
    setBusy(true); setError('')
    try { onChange(await fn()) } catch (e) { setError(sellerErrorMessage(e, fallback)) } finally { setBusy(false) }
  }
  const save = () => run(() => saveSellerApplication(payload()), 'Your application could not be saved.')
  const submit = () => run(async () => {
    await saveSellerApplication(payload())
    return submitSellerApplication(status.declaration.version)
  }, 'Your application could not be submitted.')
  const upload = () => docFile && run(async () => {
    await saveSellerApplication(payload())
    return uploadSellerDocument(docType, docFile, docExpiry || undefined)
  }, 'The document could not be uploaded.')

  return (
    <Card className="space-y-4 p-4" aria-label="Seller application">
      <h2 className="text-lg font-semibold">{business ? 'Register as a Business Seller' : 'Register as a Private Seller'}</h2>
      {app?.status === 'ACTION_REQUIRED' && app.correction_request && (
        <div role="alert" className="rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <span className="font-semibold">Please correct: </span>{app.correction_request}
        </div>
      )}
      <div>
        <Label htmlFor="sv-cat">Seller category</Label>
        <select id="sv-cat" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={form.seller_category}
                onChange={(e) => setForm((f) => ({ ...f, seller_category: e.target.value as SellerCategory, business_structure: null }))}>
          {(Object.keys(CATEGORY_LABEL) as SellerCategory[]).map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}
        </select>
        {form.seller_category === 'SOLE_TRADER' && (
          <p className="mt-1 text-xs text-gray-500">
            Operating a lawful business does not always require incorporating a company. Sole traders, and sole traders
            exempt from registration where the law allows it, are supported.
          </p>
        )}
      </div>
      {business && (
        <div>
          <Label htmlFor="sv-struct">Business structure</Label>
          <select id="sv-struct" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={form.business_structure || ''} onChange={(e) => set('business_structure', e.target.value || null)}>
            <option value="">Choose…</option>
            {form.seller_category === 'SOLE_TRADER' ? (<>
              <option value="REGISTERED">Registered sole trader</option>
              <option value="EXEMPT">Sole trader exempt from registration</option>
            </>) : (<>
              <option value="COMPANY">Company</option><option value="PARTNERSHIP">Partnership</option>
              <option value="LLP">Limited liability partnership</option><option value="ORGANISATION">Organisation</option>
              <option value="OTHER">Other</option>
            </>)}
          </select>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="sv-legal" label={form.seller_category === 'ORGANISATION' ? 'Legal name of the organisation' : 'Your full legal name'}
               value={form.legal_name} onChange={(v) => set('legal_name', v)}
               hint={form.seller_category !== 'ORGANISATION' ? 'As on your verified MyHigh5 identity.' : undefined} />
        <Field id="sv-res" label="Country of residence (2-letter code)" value={form.residence_country}
               onChange={(v) => set('residence_country', v.slice(0, 2))} />
        {business && <>
          <Field id="sv-trading" label="Trading or shop name" value={form.trading_name} onChange={(v) => set('trading_name', v)} />
          <Field id="sv-est" label="Country where the business is established (2-letter code)" value={form.establishment_country}
                 onChange={(v) => set('establishment_country', v.slice(0, 2))} />
          <Field id="sv-sub" label="State or province (if relevant)" value={form.establishment_subdivision}
                 onChange={(v) => set('establishment_subdivision', v)} />
          <Field id="sv-phone" label="Business phone" value={form.contact_phone} onChange={(v) => set('contact_phone', v)} />
        </>}
      </div>
      {business && <>
        <Field id="sv-addr" label="Business address (kept private)" value={form.business_address} multiline
               onChange={(v) => set('business_address', v)} />
        <div>
          <Label>Products or services offered</Label>
          <div className="mt-1 grid gap-1 sm:grid-cols-3">
            {status.product_categories.map((c) => (
              <label key={c} className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={(form.product_categories || []).includes(c)}
                       onChange={(e) => set('product_categories', e.target.checked
                         ? [...(form.product_categories || []), c] : (form.product_categories || []).filter((x) => x !== c))} />
                {c.replace(/_/g, ' ').toLowerCase()}{status.regulated_categories.includes(c) ? ' (regulated)' : ''}
              </label>
            ))}
          </div>
        </div>
        {!exempt ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="sv-auth" label="Registration authority" value={form.registration_authority}
                   onChange={(v) => set('registration_authority', v)} hint="For example ACRA (Singapore) or your national registry." />
            <Field id="sv-regno" label="Registration number" value={form.registration_number}
                   onChange={(v) => set('registration_number', v)} />
          </div>
        ) : (
          <Field id="sv-exempt" label="Legal basis of your registration exemption" value={form.exemption_basis} multiline
                 onChange={(v) => set('exemption_basis', v)}
                 hint="For example: business carried on only under your full legal name. Upload supporting evidence below." />
        )}
        <div className="space-y-1">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={!!form.tax_registered} onChange={(e) => set('tax_registered', e.target.checked)} />
            I am registered for a sales tax (GST/VAT) or similar
          </label>
          {form.tax_registered && (
            <Field id="sv-tax" label={`Tax identifier${app?.tax_identifier_masked ? ` (on file: ${app.tax_identifier_masked})` : ''}`}
                   value={taxId} onChange={setTaxId} hint="Stored encrypted. Never shown publicly." />
          )}
        </div>
      </>}
      {form.seller_category === 'ORGANISATION' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field id="sv-rep" label="Authorised representative (your full name)" value={form.representative?.full_name}
                 onChange={(v) => set('representative', { full_name: v, role: form.representative?.role || null })} />
          <Field id="sv-role" label="Your role" value={form.representative?.role}
                 onChange={(v) => set('representative', { full_name: form.representative?.full_name || null, role: v })} />
        </div>
      )}
      {form.seller_category === 'PRIVATE' && (
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">About your sales</legend>
          <p className="text-xs text-gray-500">Private sellers sell occasional personal belongings. Tick anything that applies.</p>
          {INDICATORS.map(([key, text]) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!form.commercial_indicators?.[key]}
                     onChange={(e) => set('commercial_indicators', { ...(form.commercial_indicators || {}), [key]: e.target.checked })} />
              {text}
            </label>
          ))}
          <p className="text-xs text-gray-500">
            MyHigh5 reviews a private seller&apos;s category after USD {status.private_review_thresholds.sales_usd} in completed
            sales or {status.private_review_thresholds.order_count} completed sales in 12 months. {status.private_review_thresholds.note}
          </p>
        </fieldset>
      )}
      {app && (
        <div className="space-y-2 rounded-md border p-3">
          <p className="text-sm font-medium">Documents</p>
          {app.documents.length === 0 ? <p className="text-xs text-gray-500">No documents uploaded.</p> : (
            <ul className="text-xs text-gray-600 dark:text-gray-300">
              {app.documents.map((d) => <li key={d.id}>{DOC_TYPE_LABEL[d.doc_type] || d.doc_type}: {d.file_name}</li>)}
            </ul>
          )}
          <div className="grid gap-2 sm:grid-cols-3">
            <select aria-label="Document type" className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                    value={docType} onChange={(e) => setDocType(e.target.value)}>
              {Object.entries(DOC_TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <Input type="file" aria-label="Document file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setDocFile(e.target.files?.[0] || null)} />
            <Input type="date" aria-label="Expiry date (optional)" value={docExpiry} onChange={(e) => setDocExpiry(e.target.value)} />
          </div>
          <Button size="sm" variant="outline" disabled={busy || !docFile} onClick={upload}><Upload className="mr-1 h-4 w-4" />Upload</Button>
          <p className="text-xs text-gray-500">PDF, JPG or PNG, up to 10 MB. Stored encrypted; seen only by the MyHigh5 review team.</p>
        </div>
      )}
      {app && app.missing_fields.length > 0 && (
        <p className="text-xs text-gray-500">Still needed: {app.missing_fields.join(', ').replace(/_/g, ' ')}</p>
      )}
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={declared} onChange={(e) => setDeclared(e.target.checked)} />
        <span>{status.declaration.text}</span>
      </label>
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" disabled={busy} onClick={save}>Save draft</Button>
        <Button disabled={busy || !declared} onClick={submit}>{busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Submit application</Button>
      </div>
    </Card>
  )
}

function Appeal({ onChange }: { onChange: (s: SellerStatus) => void }) {
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const send = async () => {
    setError('')
    try { onChange(await appealSellerDecision(text)) } catch (e) { setError(sellerErrorMessage(e, 'Your appeal could not be sent.')) }
  }
  return (
    <div className="space-y-2">
      <Label htmlFor="sv-appeal">Appeal this decision</Label>
      <Textarea id="sv-appeal" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <Button size="sm" disabled={text.trim().length < 20} onClick={send}>Send appeal</Button>
    </div>
  )
}

export function SellerRegistration() {
  const [status, setStatus] = useState<SellerStatus | null>(null)
  const [draft, setDraft] = useState<SellerApplicationInput | null>(null)
  const [error, setError] = useState('')

  const apply = (s: SellerStatus) => { setStatus(s); setDraft(fromApplication(s)) }
  const load = useCallback(async () => {
    try { apply(await getSellerStatus()) } catch (e) { setError(sellerErrorMessage(e, 'Your seller status could not be loaded.')) }
  }, [])
  useEffect(() => { load() }, [load])

  if (error) return <p role="alert" className="text-sm text-red-600">{error}</p>
  if (!status) return <Loader2 className="h-5 w-5 animate-spin" />
  const app = status.application
  const profileStatus = status.profile.status
  const canStart = !draft && !['CHECKS_IN_PROGRESS', 'MANUAL_REVIEW_REQUIRED', 'SUBMITTED', 'RESTRICTED'].includes(app?.status || '')
    && profileStatus !== 'RESTRICTED'
  const start = (category: SellerCategory) => setDraft({ seller_category: category, product_categories: [], commercial_indicators: {} })

  return (
    <div className="space-y-4">
      <Card className="space-y-2 p-4">
        <div className="flex items-center gap-2">
          <BadgeCheck className="h-5 w-5 text-primary" aria-hidden />
          <p className="font-semibold">Seller status: {SELLER_STATUS_LABEL[profileStatus] || profileStatus}</p>
        </div>
        {status.profile.public_label && <p className="text-sm">Shown to buyers as: <span className="font-medium">{status.profile.public_label}</span></p>}
        {app && app.status !== profileStatus && (
          <p className="text-sm text-gray-600 dark:text-gray-300">Latest application: {SELLER_STATUS_LABEL[app.status] || app.status}</p>
        )}
        {app?.review_status_message && <p className="text-sm text-gray-600 dark:text-gray-300">{app.review_status_message}</p>}
        {status.enforcement_enabled && !status.can_sell && (
          <p className="flex items-start gap-2 text-sm text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            You can prepare draft listings now. Publishing opens once your seller registration is approved.
          </p>
        )}
        <p className="text-xs text-gray-500">{APPROVAL_MEANING}</p>
      </Card>

      {canStart && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => start('SOLE_TRADER')}><Briefcase className="mr-2 h-4 w-4" />Register as a Business Seller</Button>
          <Button variant="outline" onClick={() => start('PRIVATE')}><User className="mr-2 h-4 w-4" />Register as a Private Seller</Button>
        </div>
      )}
      {draft && <ApplicationForm key={app?.id ?? 'new'} status={status} initial={draft} onChange={apply} />}
      {(app?.status === 'REJECTED' || (profileStatus === 'RESTRICTED' && app?.status !== 'MANUAL_REVIEW_REQUIRED')) && (
        <Card className="p-4"><Appeal onChange={apply} /></Card>
      )}
      {app && app.history.length > 0 && (
        <Card className="p-4">
          <p className="mb-2 text-sm font-medium">History</p>
          <ul className="space-y-1 text-xs text-gray-600 dark:text-gray-300">
            {app.history.map((h, i) => (
              <li key={i}>{h.at ? new Date(h.at).toLocaleString() : ''} · {SELLER_STATUS_LABEL[h.to_status] || h.to_status}{h.message ? ` — ${h.message}` : ''}</li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
