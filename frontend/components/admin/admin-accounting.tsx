'use client'

import { useState, useEffect, useCallback } from 'react'
import { useLanguage } from '@/contexts/language-context'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { format } from 'date-fns'
import { enUS, fr } from 'date-fns/locale'
import { Loader2, RefreshCw, FileText, BarChart3, TrendingUp, AlertCircle } from 'lucide-react'
import { api } from '@/lib/api-service'

const EMPTY = { chartOfAccounts: [] as any[], journalEntries: [] as any[] }

export default function AdminAccounting() {
    const { t, language } = useLanguage()
    const [activeTab, setActiveTab] = useState('journal')
    const [loading, setLoading] = useState(true)
    const [data, setData] = useState<any>(EMPTY)
    const [error, setError] = useState<Error | null>(null)
    const dateLocale = language === 'fr' ? fr : enUS
    const numberLocale = language === 'fr' ? 'fr-FR' : 'en-US'

    const loadData = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            const [coaRes, jeRes] = await Promise.all([
                api.get('/admin/accounting/chart-of-accounts'),
                api.get('/admin/accounting/journal-entries', { params: { limit: 50 } }),
            ])
            if (coaRes.status >= 400) {
                const d = coaRes.data as any
                throw new Error(typeof d?.detail === 'string' ? d.detail : 'Chart of accounts request failed')
            }
            if (jeRes.status >= 400) {
                const d = jeRes.data as any
                throw new Error(typeof d?.detail === 'string' ? d.detail : 'Journal entries request failed')
            }
            setData({
                chartOfAccounts: Array.isArray(coaRes.data) ? coaRes.data : [],
                journalEntries: Array.isArray(jeRes.data) ? jeRes.data : [],
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

    const refetch = () => {
        void loadData()
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

    const journalEntries = data?.journalEntries || []
    const chartRows = data?.chartOfAccounts || []

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
                </TabsList>

                <TabsContent value="journal" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>{t('admin.accounting.journal_title') || 'Journal Entries'}</CardTitle>
                            <CardDescription>{t('admin.accounting.journal_desc') || 'Last 50 accounting entries'}</CardDescription>
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
                                                        ? format(new Date(entry.entryDate), language === 'fr' ? 'dd/MM/yyyy HH:mm' : 'MM/dd/yyyy HH:mm', { locale: dateLocale })
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
                                        <TableHead>{t('admin.accounting.table.type') || 'Type'}</TableHead>
                                        <TableHead className="text-right">{t('admin.accounting.table.balance') || 'Balance'}</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {chartRows.length === 0 ? (
                                        <TableRow>
                                            <TableCell colSpan={4} className="text-center text-muted-foreground py-8">
                                                {t('admin.accounting.no_coa') || 'No accounts in database. Run init_chart_of_accounts on the server.'}
                                            </TableCell>
                                        </TableRow>
                                    ) : (
                                        chartRows.map((account: any) => (
                                            <TableRow key={account.id}>
                                                <TableCell className="font-mono font-medium">{account.accountCode}</TableCell>
                                                <TableCell>{account.accountName}</TableCell>
                                                <TableCell>
                                                    <Badge variant="outline">{account.accountType}</Badge>
                                                </TableCell>
                                                <TableCell className="text-right font-mono">
                                                    {Number(account.creditBalance) !== 0
                                                        ? Number(account.creditBalance).toFixed(2)
                                                        : '—'}
                                                </TableCell>
                                            </TableRow>
                                        ))
                                    )}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    )
}
