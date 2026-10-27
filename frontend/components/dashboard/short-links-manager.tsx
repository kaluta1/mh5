'use client'

import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Check, Copy, ExternalLink, Link2, Loader2, RefreshCw, Ban, UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  InvitationStatus,
  ShortLink,
  createShortLink,
  disableShortLink,
  getInvitationStatus,
  listShortLinks,
  looksLikeMyHigh5Link,
  shortLinkErrorMessage,
} from '@/lib/short-links'

export const INVITATION_HELP =
  "When enabled, eligible new members who register through this link will be attributed to you under MyHigh5's referral rules."

function formatDate(value: string | null): string {
  if (!value) return ''
  const date = new Date(value.endsWith('Z') || value.includes('+') ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

function useCopied() {
  const [copied, setCopied] = useState<string | null>(null)
  const copy = useCallback(async (key: string, text: string) => {
    if (await copyText(text)) {
      setCopied(key)
      setTimeout(() => setCopied((current) => (current === key ? null : current)), 2000)
      return true
    }
    return false
  }, [])
  return { copied, copy }
}

function InvitationBadge({ on }: { on: boolean }) {
  return on ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
      <UserPlus className="h-3 w-3" aria-hidden /> Invitation on
    </span>
  ) : (
    <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300">
      Invitation off
    </span>
  )
}

function StatusBadge({ active }: { active: boolean }) {
  return active ? (
    <span className="inline-flex items-center rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-300">
      Active
    </span>
  ) : (
    <span className="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700 dark:bg-red-900/30 dark:text-red-300">
      Disabled
    </span>
  )
}

export function ShortenLinkForm({ onCreated }: { onCreated?: (link: ShortLink) => void }) {
  const [url, setUrl] = useState('')
  const [includeInvitation, setIncludeInvitation] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<ShortLink | null>(null)
  const [invitation, setInvitation] = useState<InvitationStatus | null>(null)
  const { copied, copy } = useCopied()

  // Asked only when the member turns the invitation on; a failure to ask never blocks anything.
  useEffect(() => {
    if (!includeInvitation || invitation) return
    let cancelled = false
    getInvitationStatus()
      .then((status) => { if (!cancelled) setInvitation(status) })
      .catch(() => { /* no warning shown; the server still applies the rule at registration */ })
    return () => { cancelled = true }
  }, [includeInvitation, invitation])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError(null)
    setCreated(null)
    if (!url.trim()) {
      setError('Paste the link of a MyHigh5 page.')
      return
    }
    if (!looksLikeMyHigh5Link(url)) {
      setError('Only MyHigh5 page links (https://myhigh5.com/...) can be shortened.')
      return
    }
    setSubmitting(true)
    try {
      const link = await createShortLink(url, includeInvitation)
      setCreated(link)
      onCreated?.(link)
    } catch (err) {
      setError(shortLinkErrorMessage(err, 'The short link could not be created. Please try again.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card className="p-4 sm:p-6">
      <form onSubmit={submit} noValidate className="space-y-5" aria-label="Shorten a Link">
        <div className="space-y-2">
          <Label htmlFor="short-link-url" className="text-gray-900 dark:text-gray-100">
            Paste a MyHigh5 page link
          </Label>
          <Input
            id="short-link-url"
            type="url"
            inputMode="url"
            autoComplete="off"
            placeholder="https://myhigh5.com/..."
            value={url}
            onChange={(e) => {
              setUrl(e.target.value)
              setError(null)
            }}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'short-link-error' : undefined}
            disabled={submitting}
          />
        </div>

        <div className="flex items-start justify-between gap-4 rounded-lg border border-gray-200 p-3 dark:border-gray-700">
          <div className="space-y-1">
            <Label htmlFor="short-link-invitation" className="text-gray-900 dark:text-gray-100">
              Include my personal invitation
            </Label>
            <p id="short-link-invitation-help" className="text-sm text-gray-600 dark:text-gray-400">
              {INVITATION_HELP}
            </p>
          </div>
          <Switch
            id="short-link-invitation"
            checked={includeInvitation}
            onCheckedChange={(value) => setIncludeInvitation(Boolean(value))}
            aria-describedby="short-link-invitation-help"
            disabled={submitting}
          />
        </div>

        {includeInvitation && invitation && !invitation.eligible && invitation.message && (
          <div role="note" data-testid="invitation-warning"
            className="flex gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-900/20 dark:text-amber-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <p>
              {invitation.message}{' '}
              {invitation.reason?.startsWith('KYC') && (
                <a href="/dashboard/kyc" className="font-medium underline">Go to identity verification</a>
              )}
            </p>
          </div>
        )}

        {error && (
          <p id="short-link-error" role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">
            {error}
          </p>
        )}

        <Button type="submit" disabled={submitting} className="w-full sm:w-auto">
          {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <Link2 className="mr-2 h-4 w-4" aria-hidden />}
          {submitting ? 'Creating…' : 'Create Short Link'}
        </Button>
      </form>

      {created && (
        <div role="status" className="mt-6 space-y-3 rounded-lg border border-green-200 bg-green-50 p-4 dark:border-green-900 dark:bg-green-900/20">
          <p className="text-sm font-medium text-green-800 dark:text-green-300">
            {created.reused
              ? 'You already had this short link, so here it is again.'
              : 'Your short link is ready to share.'}{' '}
            {created.include_invitation ? 'It includes your personal invitation.' : 'It does not include an invitation.'}
          </p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <code data-testid="created-short-url" className="min-w-0 flex-1 break-all rounded bg-white px-3 py-2 text-sm text-gray-900 dark:bg-gray-900 dark:text-gray-100">
              {created.short_url}
            </code>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => copy('created', created.short_url)}>
                {copied === 'created' ? <Check className="mr-2 h-4 w-4" aria-hidden /> : <Copy className="mr-2 h-4 w-4" aria-hidden />}
                {copied === 'created' ? 'Copied' : 'Copy Link'}
              </Button>
              <Button type="button" variant="outline" asChild>
                <a href={created.short_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="mr-2 h-4 w-4" aria-hidden /> Open Link
                </a>
              </Button>
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}

export function MyShortLinks({ refreshKey = 0 }: { refreshKey?: number }) {
  const [links, setLinks] = useState<ShortLink[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<ShortLink | null>(null)
  const [disabling, setDisabling] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const { copied, copy } = useCopied()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const page = await listShortLinks()
      setLinks(page.items)
      setTotal(page.total)
    } catch (err) {
      setError(shortLinkErrorMessage(err, 'Your short links could not be loaded.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load, refreshKey])

  const confirmDisable = async () => {
    if (!pending) return
    setDisabling(true)
    setActionError(null)
    try {
      const updated = await disableShortLink(pending.id)
      setLinks((current) => current.map((l) => (l.id === updated.id ? updated : l)))
      setPending(null)
    } catch (err) {
      setActionError(shortLinkErrorMessage(err, 'The link could not be disabled. Please try again.'))
      setPending(null)
    } finally {
      setDisabling(false)
    }
  }

  return (
    <Card className="p-4 sm:p-6">
      <div className="mb-4 flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">My Short Links</h2>
        <Button type="button" variant="ghost" size="sm" onClick={load} disabled={loading} aria-label="Refresh my short links">
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} aria-hidden />
        </Button>
      </div>

      {actionError && (
        <p role="alert" className="mb-3 rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">{actionError}</p>
      )}

      {loading && links.length === 0 ? (
        <div className="flex items-center justify-center py-10 text-gray-500 dark:text-gray-400" aria-busy="true">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" aria-hidden /> Loading your short links…
        </div>
      ) : error ? (
        <div role="alert" className="rounded-md bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">
          {error}{' '}
          <button type="button" className="font-medium underline" onClick={load}>Try again</button>
        </div>
      ) : links.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-600 dark:text-gray-400">
          You have not created any short links yet. Paste a MyHigh5 page link above to create your first one.
        </p>
      ) : (
        <ul className="divide-y divide-gray-200 dark:divide-gray-800" aria-label="My short links">
          {links.map((link) => (
            <li key={link.id} className="py-4" data-testid={`short-link-${link.id}`}>
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="min-w-0 space-y-1">
                  <p className={`break-all font-mono text-sm font-medium ${link.is_active ? 'text-gray-900 dark:text-gray-100' : 'text-gray-400 line-through dark:text-gray-500'}`}>
                    {link.short_url}
                  </p>
                  <p className="break-all text-xs text-gray-600 dark:text-gray-400" title={link.destination_url}>
                    → {link.destination_url}
                  </p>
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <StatusBadge active={link.is_active} />
                    <InvitationBadge on={link.include_invitation} />
                    <span className="text-xs text-gray-500 dark:text-gray-400">Created {formatDate(link.created_at)}</span>
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Button type="button" size="sm" variant="outline" disabled={!link.is_active}
                    onClick={() => copy(`row-${link.id}`, link.short_url)}>
                    {copied === `row-${link.id}` ? <Check className="mr-1 h-4 w-4" aria-hidden /> : <Copy className="mr-1 h-4 w-4" aria-hidden />}
                    {copied === `row-${link.id}` ? 'Copied' : 'Copy'}
                  </Button>
                  {link.is_active && (
                    <Button type="button" size="sm" variant="outline" asChild>
                      <a href={link.short_url} target="_blank" rel="noopener noreferrer">
                        <ExternalLink className="mr-1 h-4 w-4" aria-hidden /> Open
                      </a>
                    </Button>
                  )}
                  {link.is_active && (
                    <Button type="button" size="sm" variant="outline"
                      className="text-red-600 hover:text-red-700 dark:text-red-400"
                      onClick={() => setPending(link)}>
                      <Ban className="mr-1 h-4 w-4" aria-hidden /> Disable
                    </Button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {total > links.length && !loading && (
        <p className="pt-3 text-xs text-gray-500 dark:text-gray-400">Showing your {links.length} most recent links of {total}.</p>
      )}

      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(open) => { if (!open) setPending(null) }}
        title="Disable this short link?"
        message="People who open it will see that the link is no longer available. This cannot be undone; you can create a new short link for the same page at any time."
        confirmText="Disable link"
        cancelText="Keep it"
        onConfirm={confirmDisable}
        isLoading={disabling}
        isDangerous
      />
    </Card>
  )
}

export function ShortLinksManager() {
  const [refreshKey, setRefreshKey] = useState(0)
  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-4 py-6 sm:px-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Shorten a Link</h1>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          Turn any shareable MyHigh5 page into a short link. A short link never changes who can see a page.
        </p>
      </div>
      <ShortenLinkForm onCreated={() => setRefreshKey((k) => k + 1)} />
      <MyShortLinks refreshKey={refreshKey} />
    </div>
  )
}
