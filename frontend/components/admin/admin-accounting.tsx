'use client'

import { useState, useEffect, useCallback } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { format } from 'date-fns'
import { LOCALE_BY_LANG, getDateFnsLocale } from '@/lib/date-utils'
import { Loader2, RefreshCw, FileText, BarChart3, TrendingUp, AlertCircle, PieChart } from 'lucide-react'
import api from '@/lib/api'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
const EMPTY = { chartOfAccounts: [] as any[], journalEntries: [] as any[] }

const JOURNAL_PAGE_SIZE = 300

/**
 * Match admin-users.tsx: accept a bare array or common envelope shapes (gateways, BFFs, older clients).
 */
function extractApiArray<T>(raw: unknown): T[] {
    if (Array.isArray(raw)) return raw as T[]
    if (raw && typeof raw === 'object') {
        const o = raw as Record<string, unknown>
        const nested =
            o.data ??
            o.items ??
            o.results ??
            o.accounts ??
            o.chartOfAccounts ??
            o.chart_of_accounts ??
            o.journalEntries ??
            o.journal_entries
        if (Array.isArray(nested)) return nested as T[]
    }
    if (typeof raw === 'string') {
        try {
            return extractApiArray(JSON.parse(raw) as unknown)
        } catch {
            return []
        }
    }
    return []
}

/** Admin CoA endpoint uses camelCase; tolerate snake_case if a proxy or alternate handler returns ORM-shaped JSON. */
function normalizeCoaRow(r: Record<string, unknown>): any {
    const id = r.id
    const accountCode = r.accountCode ?? r.account_code
    const accountName = r.accountName ?? r.account_name
    const description = r.description
    const accountType = r.accountType ?? r.account_type
    const bal = r.creditBalance ?? r.credit_balance ?? r.balance ?? r.totalLiabilities ?? r.total_liabilities
    return {
        id,
        accountCode,
        accountName,
        description: typeof description === 'string' && description.trim() ? description : null,
        accountType: accountType != null ? String(accountType).toUpperCase() : accountType,
        creditBalance: typeof bal === 'number' ? bal : Number(bal ?? 0),
        totalLiabilities: typeof bal === 'number' ? bal : Number(bal ?? 0),
    }
}

type ReportKind = 'full' | 'balance' | 'income' | 'trial' | 'cashflow' | 'ledger'

export default function AdminAccounting() {
    const { t, language } = useLanguage()
    const [activeTab, setActiveTab] = useState('journal')
    const [loading, setLoading] = useState(true)
    const [data, setData] = useState<any>(EMPTY)
    const [error, setError] = useState<Error | null>(null)
    const dateLocale = getDateFnsLocale(language)
    const numberLocale = LOCALE_BY_LANG[language] || 'en-US'

    const todayStr = format(new Date(), 'yyyy-MM-dd')
    const [reportKind, setReportKind] = useState<ReportKind>('balance')
    const [asOfDate, setAsOfDate] = useState(todayStr)
    const [periodStart, setPeriodStart] = useState(() => format(new Date(new Date().getFullYear(), 0, 1), 'yyyy-MM-dd'))
    const [periodEnd, setPeriodEnd] = useState(todayStr)
    const [glAccountCode, setGlAccountCode] = useState('')
    const [reportData, setReportData] = useState<Record<string, unknown> | null>(null)
    const [reportLoading, setReportLoading] = useState(false)
    const [reportError, setReportError] = useState<string | null>(null)

    useEffect(() => {
        setReportData(null)
        setReportError(null)
    }, [reportKind])

    const fmtMoney = (n: number) =>
        new Intl.NumberFormat(numberLocale, { style: 'currency', currency: 'USD' }).format(Number(n) || 0)

    const downloadTextFile = (filename: string, content: string, mime: string) => {
        const blob = new Blob([content], { type: mime })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        a.click()
        URL.revokeObjectURL(url)
    }

    const loadData = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            const [coaRes, jeRes] = await Promise.all([
                api.get('/api/v1/admin/accounting/chart-of-accounts'),
                api.get('/api/v1/admin/accounting/journal-entries', {
                    params: { limit: JOURNAL_PAGE_SIZE, offset: 0 },
                }),
            ])
            if (coaRes.status >= 400) {
                const d = coaRes.data as any
                throw new Error(typeof d?.detail === 'string' ? d.detail : 'Chart of accounts request failed')
            }
            if (jeRes.status >= 400) {
                const d = jeRes.data as any
                throw new Error(typeof d?.detail === 'string' ? d.detail : 'Journal entries request failed')
            }
            const coaRaw = extractApiArray<Record<string, unknown>>(coaRes.data)
            const jeRaw = extractApiArray(jeRes.data)
            setData({
                chartOfAccounts: coaRaw.map((row) => normalizeCoaRow(row)),
                journalEntries: jeRaw,
            })
        } catch (e: any) {
            setError(e instanceof Error ? e : new Error(String(e)))
            setData(EMPTY)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        void loadData()
    }, [loadData])

    const journalEntries = data?.journalEntries || []
    const chartRows = data?.chartOfAccounts || []

    useEffect(() => {
        if (chartRows.length > 0 && glAccountCode === '') {
            setGlAccountCode(String((chartRows[0] as any).accountCode ?? ''))
        }
    }, [chartRows, glAccountCode])

    const loadFinancialReport = async () => {
        setReportLoading(true)
        setReportError(null)
        try {
            let url = ''
            const params: Record<string, string> = {}
            if (reportKind === 'full') {
                url = '/api/v1/admin/accounting/full-financial-report'
                params.as_of = asOfDate
                params.period_start = periodStart
                params.period_end = periodEnd
            } else if (reportKind === 'balance') {
                url = '/api/v1/admin/accounting/balance-sheet'
                params.as_of = asOfDate
            } else if (reportKind === 'income') {
                url = '/api/v1/admin/accounting/income-statement'
                params.start_date = periodStart
                params.end_date = periodEnd
            } else if (reportKind === 'trial') {
                url = '/api/v1/admin/accounting/trial-balance'
                params.as_of = asOfDate
            } else if (reportKind === 'cashflow') {
                url = '/api/v1/admin/accounting/cash-flow-statement'
                params.start_date = periodStart
                params.end_date = periodEnd
            } else if (reportKind === 'ledger') {
                url = '/api/v1/admin/accounting/general-ledger'
                params.account_code = glAccountCode || String((chartRows[0] as any)?.accountCode ?? '')
                params.start_date = periodStart
                params.end_date = periodEnd
            }
            const res = await api.get(url, { params })
            if (res.status >= 400) {
                const d = res.data as { detail?: string }
                throw new Error(typeof d?.detail === 'string' ? d.detail : t('admin.accounting.report_failed'))
            }
            setReportData(res.data as Record<string, unknown>)
        } catch (e) {
            setReportData(null)
            setReportError(e instanceof Error ? e.message : String(e))
        } finally {
            setReportLoading(false)
        }
    }

    const refetch = () => {
        void loadData()
    }

    const loadMoreJournal = async () => {
        setLoading(true)
        setError(null)
        try {
            const offset = data?.journalEntries?.length ?? 0
            const jeRes = await api.get('/api/v1/admin/accounting/journal-entries', {
                params: { limit: JOURNAL_PAGE_SIZE, offset },
            })
            if (jeRes.status >= 400) {
                const d = jeRes.data as any
                throw new Error(typeof d?.detail === 'string' ? d.detail : 'Journal request failed')
            }
            const jeRaw = extractApiArray(jeRes.data)
            setData((prev) => ({
                chartOfAccounts: prev.chartOfAccounts,
                journalEntries: [...(prev.journalEntries || []), ...jeRaw],
            }))
        } catch (e: any) {
            setError(e instanceof Error ? e : new Error(String(e)))
        } finally {
            setLoading(false)
        }
    }

    const totalRevenue = data?.chartOfAccounts
        ?.filter((a: any) => String(a.accountType || '').toUpperCase() === 'REVENUE')
        .reduce((acc: number, curr: any) => acc + (Number(curr.creditBalance) || 0), 0) || 0

    if (loading && !data?.chartOfAccounts?.length && !data?.journalEntries?.length) {
        return (
            <div className="flex justify-center items-center h-96">
                <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
            </div>
        )
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center h-96 text-red-500">
                <AlertCircle className="h-12 w-12 mb-4" />
                <p>{t('admin.accounting.error_loading') || 'Error loading accounting data'}</p>
                <p className="text-sm text-gray-500">{error.message}</p>
                <Button onClick={() => refetch()} className="mt-4" variant="outline">
                    {t('admin.accounting.retry') || 'Retry'}
                </Button>
            </div>
        )
    }

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">{t('admin.accounting.title') || 'Accounting'}</h2>
                    <p className="text-muted-foreground">{t('admin.accounting.subtitle') || 'Financial overview and journal entries'}</p>
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => refetch()}
                    disabled={loading}
                    className="gap-2"
                >
                    <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    {t('admin.accounting.refresh') || 'Refresh'}
                </Button>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">{t('admin.accounting.total_revenue') || 'Total Revenue'}</CardTitle>
                        <TrendingUp className="h-4 w-4 text-green-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-green-600">
                            {new Intl.NumberFormat(numberLocale, { style: 'currency', currency: 'USD' }).format(totalRevenue)}
                        </div>
                        <p className="text-xs text-muted-foreground">{t('admin.accounting.ytd') || 'Year to date'}</p>
                    </CardContent>
                </Card>
            </div>

            <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
                <TabsList>
                    <TabsTrigger value="journal" className="gap-2">
                        <FileText className="h-4 w-4" />
                        {t('admin.accounting.journal_tab') || 'General Journal'}
                    </TabsTrigger>
                    <TabsTrigger value="coa" className="gap-2">
                        <BarChart3 className="h-4 w-4" />
                        {t('admin.accounting.coa_tab') || 'Chart of Accounts'}
                    </TabsTrigger>
                    <TabsTrigger value="reports" className="gap-2">
                        <PieChart className="h-4 w-4" />
                        {t('admin.accounting.reports_tab') || 'Financial reports'}
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="journal" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>{t('admin.accounting.journal_title') || 'Journal Entries'}</CardTitle>
                            <CardDescription>
                                {t('admin.accounting.journal_desc_paged') ||
                                    `Journal entries (newest first). First page: ${JOURNAL_PAGE_SIZE} rows — use Load more for older history.`}
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>{t('admin.accounting.table.date') || 'Date'}</TableHead>
                                        <TableHead>{t('admin.accounting.table.ref') || 'Ref. No.'}</TableHead>
                                        <TableHead>{t('admin.accounting.table.description') || 'Description'}</TableHead>
                                        <TableHead>{t('admin.accounting.table.debit') || 'Debit'}</TableHead>
                                        <TableHead>{t('admin.accounting.table.credit') || 'Credit'}</TableHead>
                                        <TableHead>{t('admin.accounting.table.status') || 'Status'}</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {journalEntries.length === 0 ? (
                                        <TableRow>
                                            <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                                                {t('admin.accounting.no_journal') || 'No journal entries yet.'}
                                            </TableCell>
                                        </TableRow>
                                    ) : (
                                        journalEntries.map((entry: any) => (
                                            <TableRow key={entry.id}>
                                                <TableCell>
                                                    {entry.entryDate
                                                        ? format(new Date(entry.entryDate), 'P p', { locale: dateLocale })
                                                        : '—'}
                                                </TableCell>
                                                <TableCell className="font-mono text-xs">{entry.entryNumber}</TableCell>
                                                <TableCell>
                                                    <div className="font-medium">{entry.description}</div>
                                                    <div className="text-sm text-gray-500 mt-1 space-y-1">
                                                        {(entry.lines || []).map((line: any) => (
                                                            <div key={line.id} className="flex justify-between text-xs border-b border-gray-100 dark:border-gray-800 last:border-0 pb-1">
                                                                <span>{line.account?.accountCode} - {line.account?.accountName}</span>
                                                                <span className="font-mono">
                                                                    {line.debitAmount > 0
                                                                        ? `D: ${Number(line.debitAmount).toFixed(2)}`
                                                                        : `C: ${Number(line.creditAmount).toFixed(2)}`}
                                                                </span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </TableCell>
                                                <TableCell className="font-mono">{Number(entry.totalDebit || 0).toFixed(2)}</TableCell>
                                                <TableCell className="font-mono">{Number(entry.totalCredit || 0).toFixed(2)}</TableCell>
                                                <TableCell>
                                                    <Badge variant={String(entry.status || '').toUpperCase() === 'POSTED' ? 'default' : 'secondary'}>
                                                        {String(entry.status || '').toUpperCase()}
                                                    </Badge>
                                                </TableCell>
                                            </TableRow>
                                        ))
                                    )}
                                </TableBody>
                            </Table>
                            <div className="flex flex-wrap items-center gap-3 mt-4">
                                <Button type="button" variant="secondary" size="sm" onClick={() => void loadMoreJournal()} disabled={loading}>
                                    {t('admin.accounting.load_more_journal') || 'Load more (older entries)'}
                                </Button>
                                <span className="text-sm text-muted-foreground">
                                    {t('admin.accounting.journal_showing') || 'Showing'}{' '}
                                    {journalEntries.length}{' '}
                                    {t('admin.accounting.journal_entries') || 'entries'}
                                </span>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="coa" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>{t('admin.accounting.coa_title') || 'Chart of Accounts'}</CardTitle>
                            <CardDescription>{t('admin.accounting.coa_desc') || 'List of accounts and current balances'}</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>{t('admin.accounting.table.code') || 'Code'}</TableHead>
                                        <TableHead>{t('admin.accounting.table.account') || 'Account Name'}</TableHead>
                                        <TableHead className="min-w-[200px] max-w-md">
                                            {t('admin.accounting.table.description') || 'Description'}
                                        </TableHead>
                                        <TableHead>{t('admin.accounting.table.type') || 'Type'}</TableHead>
                                        <TableHead className="text-right">{t('admin.accounting.table.balance') || 'Balance'}</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {chartRows.length === 0 ? (
                                        <TableRow>
                                            <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                                                {t('admin.accounting.no_coa') || 'No accounts in database. Run init_chart_of_accounts on the server.'}
                                            </TableCell>
                                        </TableRow>
                                    ) : (
                                        chartRows.map((account: any) => (
                                            <TableRow key={account.id}>
                                                <TableCell className="font-mono font-medium">{account.accountCode}</TableCell>
                                                <TableCell>{account.accountName}</TableCell>
                                                <TableCell
                                                    className="max-w-md text-sm text-muted-foreground align-top"
                                                    title={account.description || undefined}
                                                >
                                                    {account.description ? (
                                                        <span className="line-clamp-3 whitespace-pre-wrap break-words">
                                                            {account.description}
                                                        </span>
                                                    ) : (
                                                        '—'
                                                    )}
                                                </TableCell>
                                                <TableCell>
                                                    <Badge variant="outline">{account.accountType}</Badge>
                                                </TableCell>
                                                <TableCell className="text-right font-mono">
                                                    {Number(account.creditBalance ?? 0).toFixed(2)}
                                                </TableCell>
                                            </TableRow>
                                        ))
                                    )}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </TabsContent>

                <TabsContent value="reports" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>{t('admin.accounting.reports_tab')}</CardTitle>
                            <CardDescription>{t('admin.accounting.reports_hint')}</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            <p className="text-sm text-muted-foreground">{t('admin.accounting.full_pack_hint')}</p>
                            <div className="flex flex-wrap gap-2">
                                {(
                                    [
                                        ['full', t('admin.accounting.full_pack_tab')],
                                        ['balance', t('admin.accounting.balance_sheet_title')],
                                        ['income', t('admin.accounting.income_statement_title')],
                                        ['trial', t('admin.accounting.trial_balance_title')],
                                        ['cashflow', t('admin.accounting.cash_flow_title')],
                                        ['ledger', t('admin.accounting.general_ledger_title')],
                                    ] as const
                                ).map(([k, label]) => (
                                    <Button
                                        key={k}
                                        type="button"
                                        size="sm"
                                        variant={reportKind === k ? 'default' : 'outline'}
                                        onClick={() => setReportKind(k)}
                                    >
                                        {label}
                                    </Button>
                                ))}
                            </div>

                                                       <div className="flex flex-wrap items-end gap-4">
                                {(reportKind === 'balance' || reportKind === 'trial') && (
                                    <div className="space-y-2">
                                        <Label>{t('admin.accounting.as_of_date')}</Label>
                                        <Input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} className="w-[180px]" />
                                    </div>
                                )}
                                {reportKind === 'full' && (
                                    <>
                                        <div className="space-y-2">
                                            <Label>{t('admin.accounting.as_of_date')}</Label>
                                            <Input type="date" value={asOfDate} onChange={(e) => setAsOfDate(e.target.value)} className="w-[180px]" />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>{t('admin.accounting.period_from')}</Label>
                                            <Input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} className="w-[180px]" />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>{t('admin.accounting.period_to')}</Label>
                                            <Input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} className="w-[180px]" />
                                        </div>
                                    </>
                                )}
                                {(reportKind === 'income' || reportKind === 'cashflow' || reportKind === 'ledger') && (
                                    <>
                                        <div className="space-y-2">
                                            <Label>{t('admin.accounting.period_from')}</Label>
                                            <Input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} className="w-[180px]" />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>{t('admin.accounting.period_to')}</Label>
                                            <Input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} className="w-[180px]" />
                                        </div>
                                    </>
                                )}
                                {reportKind === 'ledger' && chartRows.length > 0 && (
                                    <div className="space-y-2 min-w-[200px]">
                                        <Label>{t('admin.accounting.select_account')}</Label>
                                        <Select value={glAccountCode} onValueChange={setGlAccountCode}>
                                            <SelectTrigger>
                                                <SelectValue placeholder="—" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {chartRows.map((row: any) => (
                                                    <SelectItem key={row.id} value={String(row.accountCode)}>
                                                        {row.accountCode} — {row.accountName}
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                )}
                                <Button type="button" onClick={() => void loadFinancialReport()} disabled={reportLoading}>
                                    {reportLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2 inline" /> : null}
                                    {t('admin.accounting.load_report')}
                                </Button>
                                {reportKind === 'full' && reportData && (
                                    <>
                                        <Button
                                            type="button"
                                            variant="secondary"
                                            onClick={() =>
                                                downloadTextFile(
                                                    `full-financial-report-${asOfDate}.json`,
                                                    JSON.stringify(reportData, null, 2),
                                                    'application/json'
                                                )
                                            }
                                        >
                                            {t('admin.accounting.download_json')}
                                        </Button>
                                        <Button
                                            type="button"
                                            variant="secondary"
                                            onClick={() => {
                                                const reg = (reportData as any).chart_of_accounts_register?.accounts as any[] | undefined
                                                if (!reg?.length) return
                                                const esc = (v: string | number | null | undefined) => {
                                                    const s = String(v ?? '')
                                                    if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`
                                                    return s
                                                }
                                                const head = [
                                                    'account_code',
                                                    'account_name',
                                                    'description',
                                                    'account_type',
                                                    'parent_account_code',
                                                    'total_debit',
                                                    'total_credit',
                                                    'signed_balance',
                                                ]
                                                const lines = [
                                                    head.join(','),
                                                    ...reg.map((r) =>
                                                        [
                                                            r.account_code,
                                                            r.account_name,
                                                            r.description ?? '',
                                                            r.account_type,
                                                            r.parent_account_code ?? '',
                                                            r.total_debit,
                                                            r.total_credit,
                                                            r.signed_balance,
                                                        ]
                                                            .map(esc)
                                                            .join(',')
                                                    ),
                                                ]
                                                downloadTextFile(`coa-register-${asOfDate}.csv`, lines.join('\n'), 'text/csv;charset=utf-8')
                                            }}
                                        >
                                            {t('admin.accounting.download_coa_csv')}
                                        </Button>
                                    </>
                                )}
                            </div>

                            {reportError && (
                                <p className="text-sm text-red-600 dark:text-red-400">{reportError}</p>
                            )}

                            {reportData && reportKind === 'full' && (
                                <div className="space-y-10 border-t pt-6">
                                    {(() => {
                                        const pack = reportData as any
                                        const bs = pack.balance_sheet
                                        const inc = pack.income_statement
                                        const tb = pack.trial_balance
                                        const cf = pack.cash_flow_statement
                                        const reg = pack.chart_of_accounts_register
                                        const act = pack.period_activity_by_account
                                        const sum = pack.summary
                                        const eq = pack.equity_highlights
                                        return (
                                            <>
                                                <div className="flex flex-wrap justify-between gap-2">
                                                    <p className="text-sm text-muted-foreground">
                                                        {pack.generated_at ? `Generated: ${pack.generated_at}` : null}
                                                    </p>
                                                </div>
                                                <div>
                                                    <h4 className="font-semibold mb-2">{t('admin.accounting.summary_checks')}</h4>
                                                    <ul className="text-sm space-y-1 list-disc pl-5">
                                                        <li>
                                                            Trial balance debits = credits:{' '}
                                                            {sum?.trial_balance_debits_equal_credits ? 'OK' : 'No'} (Δ{' '}
                                                            {fmtMoney(sum?.trial_balance_difference ?? 0)})
                                                        </li>
                                                        <li>
                                                            Balance sheet A = L + E:{' '}
                                                            {sum?.balance_sheet_equation_holds ? 'OK' : 'No'} (Δ{' '}
                                                            {fmtMoney(sum?.balance_sheet_equation_difference ?? 0)})
                                                        </li>
                                                        <li>
                                                            CoA accounts: {sum?.accounts_in_chart_of_accounts ?? 0} — with period
                                                            postings: {sum?.accounts_with_period_postings ?? 0}
                                                        </li>
                                                    </ul>
                                                </div>
                                                <div>
                                                    <h4 className="font-semibold mb-2">{t('admin.accounting.balance_sheet_title')}</h4>
                                                    <p className="text-xs text-muted-foreground mb-2">{bs?.as_of_date}</p>
                                                    <div className="grid md:grid-cols-3 gap-4">
                                                        {(['assets', 'liabilities', 'equity'] as const).map((sec) => (
                                                            <Table key={sec}>
                                                                <TableHeader>
                                                                    <TableRow>
                                                                        <TableHead>{t('admin.accounting.table.account')}</TableHead>
                                                                        <TableHead className="text-right">{t('admin.accounting.table.balance')}</TableHead>
                                                                    </TableRow>
                                                                </TableHeader>
                                                                <TableBody>
                                                                    {(((bs?.[sec] as any[]) || []) as any[]).map((row: any) => (
                                                                        <TableRow key={row.account_code}>
                                                                            <TableCell className="text-xs">
                                                                                <span className="font-mono">{row.account_code}</span>
                                                                                <div className="text-muted-foreground">{row.account_name}</div>
                                                                                {row.parent_account_code ? (
                                                                                    <div className="text-[10px] text-muted-foreground">
                                                                                        {t('admin.accounting.parent_code')}: {row.parent_account_code}
                                                                                    </div>
                                                                                ) : null}
                                                                            </TableCell>
                                                                            <TableCell className="text-right font-mono">{fmtMoney(row.balance)}</TableCell>
                                                                        </TableRow>
                                                                    ))}
                                                                </TableBody>
                                                            </Table>
                                                        ))}
                                                    </div>
                                                    <p className="text-sm mt-2 font-medium">
                                                        {t('admin.accounting.total_assets')}: {fmtMoney(bs?.total_assets)} —{' '}
                                                        {t('admin.accounting.total_liabilities')}: {fmtMoney(bs?.total_liabilities)} —{' '}
                                                        {t('admin.accounting.total_equity')}: {fmtMoney(bs?.total_equity)}
                                                    </p>
                                                </div>
                                                <div>
                                                    <h4 className="font-semibold mb-2">{t('admin.accounting.income_statement_title')}</h4>
                                                    <p className="text-xs text-muted-foreground mb-2">
                                                        {inc?.period_start} — {inc?.period_end}
                                                    </p>
                                                    <div className="grid md:grid-cols-2 gap-4">
                                                        <Table>
                                                            <TableHeader>
                                                                <TableRow>
                                                                    <TableHead>{t('admin.accounting.revenues')}</TableHead>
                                                                    <TableHead className="text-right">{t('admin.accounting.table.balance')}</TableHead>
                                                                </TableRow>
                                                            </TableHeader>
                                                            <TableBody>
                                                                {(((inc?.revenues as any[]) || []) as any[]).map((row: any) => (
                                                                    <TableRow key={row.account_code}>
                                                                        <TableCell className="text-xs font-mono">{row.account_code}</TableCell>
                                                                        <TableCell className="text-right font-mono">{fmtMoney(row.amount)}</TableCell>
                                                                    </TableRow>
                                                                ))}
                                                            </TableBody>
                                                        </Table>
                                                        <Table>
                                                            <TableHeader>
                                                                <TableRow>
                                                                    <TableHead>{t('admin.accounting.expenses')}</TableHead>
                                                                    <TableHead className="text-right">{t('admin.accounting.table.balance')}</TableHead>
                                                                </TableRow>
                                                            </TableHeader>
                                                            <TableBody>
                                                                {(((inc?.expenses as any[]) || []) as any[]).map((row: any) => (
                                                                    <TableRow key={row.account_code}>
                                                                        <TableCell className="text-xs font-mono">{row.account_code}</TableCell>
                                                                        <TableCell className="text-right font-mono">{fmtMoney(row.amount)}</TableCell>
                                                                    </TableRow>
                                                                ))}
                                                            </TableBody>
                                                        </Table>
                                                    </div>
                                                    <p className="text-sm font-semibold mt-2">
                                                        {t('admin.accounting.net_income')}: {fmtMoney(inc?.net_income)}
                                                    </p>
                                                </div>
                                                <div>
                                                    <h4 className="font-semibold mb-2">{t('admin.accounting.trial_balance_title')}</h4>
                                                    <p className="text-xs text-muted-foreground mb-2">{tb?.as_of_date}</p>
                                                    <div className="max-h-64 overflow-auto border rounded-md">
                                                        <Table>
                                                            <TableHeader>
                                                                <TableRow>
                                                                    <TableHead>{t('admin.accounting.table.code')}</TableHead>
                                                                    <TableHead>{t('admin.accounting.table.debit')}</TableHead>
                                                                    <TableHead>{t('admin.accounting.table.credit')}</TableHead>
                                                                </TableRow>
                                                            </TableHeader>
                                                            <TableBody>
                                                                {(((tb?.accounts as any[]) || []) as any[]).map((row: any) => (
                                                                    <TableRow key={row.account_code}>
                                                                        <TableCell className="text-xs font-mono">{row.account_code}</TableCell>
                                                                        <TableCell className="text-right font-mono">{fmtMoney(row.debit)}</TableCell>
                                                                        <TableCell className="text-right font-mono">{fmtMoney(row.credit)}</TableCell>
                                                                    </TableRow>
                                                                ))}
                                                            </TableBody>
                                                        </Table>
                                                    </div>
                                                </div>
                                                <div>
                                                    <h4 className="font-semibold mb-2">{t('admin.accounting.cash_flow_title')}</h4>
                                                    {cf?.note ? (
                                                        <p className="text-xs text-muted-foreground mb-2">
                                                            {t('admin.accounting.note')}: {cf.note}
                                                        </p>
                                                    ) : null}
                                                    <p className="text-sm">
                                                        {t('admin.accounting.treasury_change_1001')}: {fmtMoney(cf?.net_change_in_cash)} —{' '}
                                                        {t('admin.accounting.net_income')}: {fmtMoney(cf?.net_income)}
                                                    </p>
                                                </div>
                                                <div>
                                                    <h4 className="font-semibold mb-2">{t('admin.accounting.equity_highlights')}</h4>
                                                    <p className="text-sm">
                                                        {t('admin.accounting.net_income')}: {fmtMoney(eq?.net_income_for_period)} —{' '}
                                                        {t('admin.accounting.total_equity')}: {fmtMoney(eq?.total_equity_per_balance_sheet)}
                                                    </p>
                                                    {eq?.note ? <p className="text-xs text-muted-foreground mt-1">{eq.note}</p> : null}
                                                </div>
                                                <div>
                                                    <h4 className="font-semibold mb-2">{t('admin.accounting.coa_register_title')}</h4>
                                                    <div className="max-h-96 overflow-auto border rounded-md">
                                                        <Table>
                                                            <TableHeader>
                                                                <TableRow>
                                                                    <TableHead>{t('admin.accounting.table.code')}</TableHead>
                                                                    <TableHead>{t('admin.accounting.table.type')}</TableHead>
                                                                    <TableHead>{t('admin.accounting.parent_code')}</TableHead>
                                                                    <TableHead className="text-right">{t('admin.accounting.table.debit')}</TableHead>
                                                                    <TableHead className="text-right">{t('admin.accounting.table.credit')}</TableHead>
                                                                    <TableHead className="text-right">{t('admin.accounting.table.balance')}</TableHead>
                                                                </TableRow>
                                                            </TableHeader>
                                                            <TableBody>
                                                                {(((reg?.accounts as any[]) || []) as any[]).map((row: any) => (
                                                                    <TableRow key={row.account_code}>
                                                                        <TableCell className="text-xs">
                                                                            <span className="font-mono">{row.account_code}</span>
                                                                            <div className="text-muted-foreground truncate max-w-[180px]">{row.account_name}</div>
                                                                        </TableCell>
                                                                        <TableCell className="text-xs">{row.account_type}</TableCell>
                                                                        <TableCell className="text-xs font-mono">{row.parent_account_code ?? '—'}</TableCell>
                                                                        <TableCell className="text-right font-mono text-xs">{fmtMoney(row.total_debit)}</TableCell>
                                                                        <TableCell className="text-right font-mono text-xs">{fmtMoney(row.total_credit)}</TableCell>
                                                                        <TableCell className="text-right font-mono text-xs">{fmtMoney(row.signed_balance)}</TableCell>
                                                                    </TableRow>
                                                                ))}
                                                            </TableBody>
                                                        </Table>
                                                    </div>
                                                    {reg?.subtotals_by_type ? (
                                                        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-3 text-xs">
                                                            {Object.entries(reg.subtotals_by_type).map(([k, v]: [string, any]) => (
                                                                <div key={k} className="border rounded-md p-2 bg-muted/30">
                                                                    <div className="font-semibold">{k}</div>
                                                                    <div>
                                                                        {t('admin.accounting.table.balance')}: {fmtMoney(v.signed_balance)}
                                                                    </div>
                                                                    <div>#{Math.round(v.account_count ?? 0)}</div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    ) : null}
                                                </div>
                                                <div>
                                                    <h4 className="font-semibold mb-2">{t('admin.accounting.period_activity_title')}</h4>
                                                    <p className="text-xs text-muted-foreground mb-2">
                                                        {act?.period_start} — {act?.period_end}
                                                    </p>
                                                    <div className="max-h-72 overflow-auto border rounded-md">
                                                        <Table>
                                                            <TableHeader>
                                                                <TableRow>
                                                                    <TableHead>{t('admin.accounting.table.code')}</TableHead>
                                                                    <TableHead>{t('admin.accounting.table.type')}</TableHead>
                                                                    <TableHead className="text-right">{t('admin.accounting.table.debit')}</TableHead>
                                                                    <TableHead className="text-right">{t('admin.accounting.table.credit')}</TableHead>
                                                                    <TableHead className="text-right">Net</TableHead>
                                                                </TableRow>
                                                            </TableHeader>
                                                            <TableBody>
                                                                {(((act?.lines as any[]) || []) as any[]).map((row: any) => (
                                                                    <TableRow key={row.account_code}>
                                                                        <TableCell className="text-xs font-mono">{row.account_code}</TableCell>
                                                                        <TableCell className="text-xs">{row.account_type}</TableCell>
                                                                        <TableCell className="text-right font-mono text-xs">{fmtMoney(row.period_debit)}</TableCell>
                                                                        <TableCell className="text-right font-mono text-xs">{fmtMoney(row.period_credit)}</TableCell>
                                                                        <TableCell className="text-right font-mono text-xs">{fmtMoney(row.period_net_signed)}</TableCell>
                                                                    </TableRow>
                                                                ))}
                                                            </TableBody>
                                                        </Table>
                                                    </div>
                                                </div>
                                            </>
                                        )
                                    })()}
                                </div>
                            )}

                            {reportData && reportKind === 'balance' && (
                                <div className="space-y-6">
                                    <p className="text-sm text-muted-foreground">
                                        {(reportData as any).as_of_date} —{' '}
                                        {(reportData as any).is_balanced ? t('admin.accounting.balanced_ok') : t('admin.accounting.balanced_no')}
                                    </p>
                                    <div className="grid md:grid-cols-3 gap-6">
                                        {(['assets', 'liabilities', 'equity'] as const).map((sec) => (
                                            <div key={sec} className="space-y-2">
                                                <h4 className="font-semibold">
                                                    {sec === 'assets'
                                                        ? t('admin.accounting.section_assets')
                                                        : sec === 'liabilities'
                                                          ? t('admin.accounting.section_liabilities')
                                                          : t('admin.accounting.section_equity')}
                                                </h4>
                                                <Table>
                                                    <TableBody>
                                                        {((reportData as any)[sec] as any[] | undefined)?.length ? (
                                                            ((reportData as any)[sec] as any[]).map((row: any) => (
                                                                <TableRow key={row.account_code}>
                                                                    <TableCell className="text-xs">
                                                                        <span className="font-mono">{row.account_code}</span>
                                                                        <div className="text-muted-foreground">{row.account_name}</div>
                                                                    </TableCell>
                                                                    <TableCell className="text-right font-mono">{fmtMoney(row.balance)}</TableCell>
                                                                </TableRow>
                                                            ))
                                                        ) : (
                                                            <TableRow>
                                                                <TableCell colSpan={2} className="text-muted-foreground text-sm">
                                                                    {t('admin.accounting.no_report_data')}
                                                                </TableCell>
                                                            </TableRow>
                                                        )}
                                                    </TableBody>
                                                </Table>
                                            </div>
                                        ))}
                                    </div>
                                    <div className="flex flex-wrap gap-6 text-sm font-medium border-t pt-4">
                                        <span>{t('admin.accounting.total_assets')}: {fmtMoney((reportData as any).total_assets)}</span>
                                        <span>{t('admin.accounting.total_liabilities')}: {fmtMoney((reportData as any).total_liabilities)}</span>
                                        <span>{t('admin.accounting.total_equity')}: {fmtMoney((reportData as any).total_equity)}</span>
                                    </div>
                                </div>
                            )}

                            {reportData && reportKind === 'income' && (
                                <div className="space-y-4">
                                    <p className="text-sm text-muted-foreground">
                                        {(reportData as any).period_start} — {(reportData as any).period_end}
                                    </p>
                                    <div className="grid md:grid-cols-2 gap-6">
                                        <div>
                                            <h4 className="font-semibold mb-2">{t('admin.accounting.revenues')}</h4>
                                            <Table>
                                                <TableBody>
                                                    {(((reportData as any).revenues as any[]) || []).map((row: any) => (
                                                        <TableRow key={row.account_code}>
                                                            <TableCell className="text-xs">
                                                                <span className="font-mono">{row.account_code}</span>
                                                                <div className="text-muted-foreground">{row.account_name}</div>
                                                            </TableCell>
                                                            <TableCell className="text-right font-mono">{fmtMoney(row.amount)}</TableCell>
                                                        </TableRow>
                                                    ))}
                                                </TableBody>
                                            </Table>
                                            <p className="text-right font-medium mt-2">
                                                {t('admin.accounting.statement_total_revenue')}: {fmtMoney((reportData as any).total_revenue)}
                                            </p>
                                        </div>
                                        <div>
                                            <h4 className="font-semibold mb-2">{t('admin.accounting.expenses')}</h4>
                                            <Table>
                                                <TableBody>
                                                    {(((reportData as any).expenses as any[]) || []).map((row: any) => (
                                                        <TableRow key={row.account_code}>
                                                            <TableCell className="text-xs">
                                                                <span className="font-mono">{row.account_code}</span>
                                                                <div className="text-muted-foreground">{row.account_name}</div>
                                                            </TableCell>
                                                            <TableCell className="text-right font-mono">{fmtMoney(row.amount)}</TableCell>
                                                        </TableRow>
                                                    ))}
                                                </TableBody>
                                            </Table>
                                            <p className="text-right font-medium mt-2">
                                                {t('admin.accounting.statement_total_expenses')}: {fmtMoney((reportData as any).total_expenses)}
                                            </p>
                                        </div>
                                    </div>
                                    <p className="text-lg font-semibold border-t pt-4">
                                        {t('admin.accounting.net_income')}: {fmtMoney((reportData as any).net_income)}
                                    </p>
                                </div>
                            )}

                            {reportData && reportKind === 'trial' && (
                                <div className="space-y-4">
                                    <p className="text-sm text-muted-foreground">
                                        {(reportData as any).as_of_date} —{' '}
                                        {(reportData as any).is_balanced ? t('admin.accounting.trial_balanced') : t('admin.accounting.trial_not_balanced')}
                                    </p>
                                    <Table>
                                        <TableHeader>
                                            <TableRow>
                                                <TableHead>{t('admin.accounting.table.code')}</TableHead>
                                                <TableHead>{t('admin.accounting.table.account')}</TableHead>
                                                <TableHead>{t('admin.accounting.table.type')}</TableHead>
                                                <TableHead className="text-right">{t('admin.accounting.table.debit')}</TableHead>
                                                <TableHead className="text-right">{t('admin.accounting.table.credit')}</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {(((reportData as any).accounts as any[]) || []).map((row: any) => (
                                                <TableRow key={row.account_code}>
                                                    <TableCell className="font-mono">{row.account_code}</TableCell>
                                                    <TableCell>{row.account_name}</TableCell>
                                                    <TableCell>{row.account_type}</TableCell>
                                                    <TableCell className="text-right font-mono">{fmtMoney(row.debit)}</TableCell>
                                                    <TableCell className="text-right font-mono">{fmtMoney(row.credit)}</TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                    <p className="text-sm font-medium">
                                        {t('admin.accounting.total_debits')}: {fmtMoney((reportData as any).total_debits)} —{' '}
                                        {t('admin.accounting.total_credits')}: {fmtMoney((reportData as any).total_credits)}
                                    </p>
                                </div>
                            )}

                            {reportData && reportKind === 'cashflow' && (
                                <div className="space-y-4">
                                    {(reportData as any).note && (
                                        <p className="text-sm text-muted-foreground">
                                            <span className="font-medium">{t('admin.accounting.note')}: </span>
                                            {(reportData as any).note}
                                        </p>
                                    )}
                                    <p className="text-sm">
                                        {t('admin.accounting.cf_1001_opening')}: {fmtMoney((reportData as any).beginning_cash_balance)} —{' '}
                                        {t('admin.accounting.cf_1001_closing')}: {fmtMoney((reportData as any).ending_cash_balance)}
                                    </p>
                                    <h4 className="font-semibold">{t('admin.accounting.operating')}</h4>
                                    <Table>
                                        <TableBody>
                                            {(((reportData as any).operating_activities as any[]) || []).map((row: any, i: number) => (
                                                <TableRow key={i}>
                                                    <TableCell>{row.label}</TableCell>
                                                    <TableCell className="text-right font-mono">{fmtMoney(row.amount)}</TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                    <p className="font-medium">
                                        {t('admin.accounting.net_income')}: {fmtMoney((reportData as any).net_income)} —{' '}
                                        {t('admin.accounting.treasury_change_1001')}:{' '}
                                        {fmtMoney((reportData as any).net_change_in_cash)}
                                    </p>
                                </div>
                            )}

                            {reportData && reportKind === 'ledger' && (
                                <div className="space-y-4">
                                    {(reportData as any).error && (
                                        <p className="text-sm text-amber-600">{(reportData as any).error}</p>
                                    )}
                                    {(reportData as any).account && (
                                        <p className="text-sm font-medium">
                                            {(reportData as any).account.account_code} — {(reportData as any).account.account_name}
                                            <span className="text-muted-foreground ml-2">({(reportData as any).account.account_type})</span>
                                        </p>
                                    )}
                                    <p className="text-sm">
                                        {t('admin.accounting.opening_balance')}: {fmtMoney((reportData as any).opening_balance)} —{' '}
                                        {t('admin.accounting.closing_balance')}: {fmtMoney((reportData as any).closing_balance)}
                                    </p>
                                    <h4 className="font-semibold">{t('admin.accounting.gl_lines')}</h4>
                                    <Table>
                                        <TableHeader>
                                            <TableRow>
                                                <TableHead>{t('admin.accounting.table.date')}</TableHead>
                                                <TableHead>{t('admin.accounting.table.ref')}</TableHead>
                                                <TableHead>{t('admin.accounting.table.description')}</TableHead>
                                                <TableHead className="text-right">{t('admin.accounting.table.debit')}</TableHead>
                                                <TableHead className="text-right">{t('admin.accounting.table.credit')}</TableHead>
                                                <TableHead className="text-right">{t('admin.accounting.table.balance')}</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {((reportData as any).lines as any[])?.length ? (
                                                ((reportData as any).lines as any[]).map((row: any, i: number) => (
                                                    <TableRow key={i}>
                                                        <TableCell className="text-xs whitespace-nowrap">
                                                            {row.entry_date
                                                                ? format(new Date(row.entry_date), 'yyyy-MM-dd', { locale: dateLocale })
                                                                : '—'}
                                                        </TableCell>
                                                        <TableCell className="font-mono text-xs">{row.entry_number}</TableCell>
                                                        <TableCell className="text-xs max-w-[240px] truncate">{row.description}</TableCell>
                                                        <TableCell className="text-right font-mono text-xs">{fmtMoney(row.debit)}</TableCell>
                                                        <TableCell className="text-right font-mono text-xs">{fmtMoney(row.credit)}</TableCell>
                                                        <TableCell className="text-right font-mono text-xs">{fmtMoney(row.balance)}</TableCell>
                                                    </TableRow>
                                                ))
                                            ) : (
                                                <TableRow>
                                                    <TableCell colSpan={6} className="text-muted-foreground">
                                                        {t('admin.accounting.no_report_data')}
                                                    </TableCell>
                                                </TableRow>
                                            )}
                                        </TableBody>
                                    </Table>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    )
}
