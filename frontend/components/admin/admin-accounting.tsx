'use client'

import { useEffect, useMemo, useState } from 'react'
import { format } from 'date-fns'
import type { Locale } from 'date-fns'
import { enUS, fr } from 'date-fns/locale'
import {
  AlertCircle,
  BarChart3,
  BookOpen,
  CalendarRange,
  FileSpreadsheet,
  Loader2,
  RefreshCw,
  Scale,
  Wallet,
} from 'lucide-react'

import api from '@/lib/api'
import { useLanguage } from '@/contexts/language-context'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

type AccountType = 'asset' | 'liability' | 'equity' | 'revenue' | 'expense' | 'ASSET' | 'LIABILITY' | 'EQUITY' | 'REVENUE' | 'EXPENSE'

interface AccountSummary {
  id: number
  account_code: string
  account_name: string
  account_type: AccountType
  description?: string | null
  parent_id?: number | null
  is_active: boolean
  normal_balance: string
  statement_section?: string | null
  report_group?: string | null
  sort_order: number
  is_contra_account: boolean
  opening_balance: number
  total_debit: number
  total_credit: number
  balance: number
}

interface JournalLine {
  id: number
  account_id: number
  account_code: string
  account_name: string
  description?: string | null
  debit_amount: number
  credit_amount: number
}

interface JournalEntry {
  id: number
  entry_number: string
  entry_date: string
  description: string
  reference_number?: string | null
  source_document?: string | null
  event_type?: string | null
  source_type?: string | null
  source_id?: string | null
  source_ref?: string | null
  total_debit: number
  total_credit: number
  status: string
  posted_at?: string | null
  lines: JournalLine[]
}

interface JournalEntryPage {
  items: JournalEntry[]
  total: number
  skip: number
  limit: number
}

interface TrialBalanceSummary {
  accounts: AccountSummary[]
  as_of_date?: string | null
  total_debits: number
  total_credits: number
  is_balanced: boolean
}

interface AccountingOverview {
  period_start?: string | null
  period_end?: string | null
  total_assets: number
  total_liabilities: number
  total_equity: number
  total_revenue: number
  total_contra_revenue: number
  net_revenue: number
  total_cost_of_sales: number
  total_expenses: number
  operating_income: number
  wallet_liability: number
  commission_payable: number
  prize_payable: number
  deferred_membership_revenue: number
  deferred_service_revenue: number
  journal_entry_count: number
  latest_entry_at?: string | null
}

interface GeneralLedgerLine {
  entry_id: number
  entry_number: string
  entry_date: string
  account_code: string
  account_name: string
  description?: string | null
  source_type?: string | null
  source_id?: string | null
  reference_number?: string | null
  debit_amount: number
  credit_amount: number
  running_balance: number
}

interface GeneralLedgerReport {
  account_code?: string | null
  start_date?: string | null
  end_date?: string | null
  opening_balance: number
  closing_balance: number
  lines: GeneralLedgerLine[]
}

interface StatementLine {
  account_code: string
  account_name: string
  amount: number
  statement_section?: string | null
  report_group?: string | null
}

interface IncomeStatementReport {
  start_date: string
  end_date: string
  revenue: StatementLine[]
  contra_revenue: StatementLine[]
  net_revenue: number
  cost_of_sales: StatementLine[]
  gross_profit: number
  operating_expenses: StatementLine[]
  operating_income: number
}

interface BalanceSheetReport {
  as_of_date: string
  assets: StatementLine[]
  liabilities: StatementLine[]
  equity: StatementLine[]
  total_assets: number
  total_liabilities: number
  total_equity: number
  is_balanced: boolean
}

interface ReconciliationItem {
  source_type: string
  source_id: string
  entry_count: number
  total_debit: number
  total_credit: number
  latest_entry_at?: string | null
  reference_number?: string | null
  description?: string | null
}

interface ReconciliationReport {
  source_type?: string | null
  items: ReconciliationItem[]
}

interface AccountingData {
  summary: AccountingOverview
  chartOfAccounts: AccountSummary[]
  journalEntries: JournalEntryPage
  trialBalance: TrialBalanceSummary
  generalLedger: GeneralLedgerReport
  incomeStatement: IncomeStatementReport
  balanceSheet: BalanceSheetReport
  reconciliation: ReconciliationReport
}

const today = new Date()
const startOfYear = `${today.getFullYear()}-01-01`
const todayIso = today.toISOString().slice(0, 10)

const EMPTY_DATA: AccountingData = {
  summary: {
    total_assets: 0,
    total_liabilities: 0,
    total_equity: 0,
    total_revenue: 0,
    total_contra_revenue: 0,
    net_revenue: 0,
    total_cost_of_sales: 0,
    total_expenses: 0,
    operating_income: 0,
    wallet_liability: 0,
    commission_payable: 0,
    prize_payable: 0,
    deferred_membership_revenue: 0,
    deferred_service_revenue: 0,
    journal_entry_count: 0,
    latest_entry_at: null,
    period_start: null,
    period_end: null,
  },
  chartOfAccounts: [],
  journalEntries: {
    items: [],
    total: 0,
    skip: 0,
    limit: 50,
  },
  trialBalance: {
    accounts: [],
    as_of_date: null,
    total_debits: 0,
    total_credits: 0,
    is_balanced: true,
  },
  generalLedger: {
    account_code: null,
    start_date: null,
    end_date: null,
    opening_balance: 0,
    closing_balance: 0,
    lines: [],
  },
  incomeStatement: {
    start_date: `${startOfYear}T00:00:00`,
    end_date: `${todayIso}T23:59:59`,
    revenue: [],
    contra_revenue: [],
    net_revenue: 0,
    cost_of_sales: [],
    gross_profit: 0,
    operating_expenses: [],
    operating_income: 0,
  },
  balanceSheet: {
    as_of_date: `${todayIso}T23:59:59`,
    assets: [],
    liabilities: [],
    equity: [],
    total_assets: 0,
    total_liabilities: 0,
    total_equity: 0,
    is_balanced: true,
  },
  reconciliation: {
    source_type: null,
    items: [],
  },
}

const FINANCE_LINKS = [
  { label: 'Summary', value: 'summary' },
  { label: 'Chart', value: 'coa' },
  { label: 'Journal', value: 'journal' },
  { label: 'Trial Balance', value: 'trial-balance' },
  { label: 'General Ledger', value: 'general-ledger' },
  { label: 'Statements', value: 'statements' },
  { label: 'Reconciliation', value: 'reconciliation' },
]

function formatDateTime(value: string | null | undefined, language: string, locale: Locale) {
  if (!value) return 'n/a'
  return format(new Date(value), language === 'fr' ? 'dd/MM/yyyy HH:mm' : 'MM/dd/yyyy HH:mm', { locale })
}

export default function AdminAccounting() {
  const { t, language } = useLanguage()
  const [activeTab, setActiveTab] = useState('summary')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [data, setData] = useState<AccountingData>(EMPTY_DATA)
  const [startDate, setStartDate] = useState(startOfYear)
  const [endDate, setEndDate] = useState(todayIso)
  const [ledgerAccountCode, setLedgerAccountCode] = useState('')
  const [reconciliationFilter, setReconciliationFilter] = useState('all')

  const dateLocale = language === 'fr' ? fr : enUS
  const numberLocale = language === 'fr' ? 'fr-FR' : 'en-US'

  const currencyFormatter = useMemo(
    () => new Intl.NumberFormat(numberLocale, { style: 'currency', currency: 'USD' }),
    [numberLocale]
  )

  const isoStart = `${startDate}T00:00:00`
  const isoEnd = `${endDate}T23:59:59`

  const refetch = async () => {
    try {
      setLoading(true)
      setError(null)

      const params = new URLSearchParams({
        start_date: isoStart,
        end_date: isoEnd,
      })
      const ledgerParams = new URLSearchParams({
        start_date: isoStart,
        end_date: isoEnd,
      })
      if (ledgerAccountCode.trim()) {
        ledgerParams.append('account_code', ledgerAccountCode.trim())
      }
      const reconciliationParams = new URLSearchParams()
      if (reconciliationFilter !== 'all') {
        reconciliationParams.append('source_type', reconciliationFilter)
      }

      const [
        summaryResponse,
        chartResponse,
        journalResponse,
        trialBalanceResponse,
        ledgerResponse,
        incomeResponse,
        balanceSheetResponse,
        reconciliationResponse,
      ] = await Promise.all([
        api.get(`/api/v1/accounting/summary?${params.toString()}`),
        api.get(`/api/v1/accounting/chart-of-accounts?${params.toString()}`),
        api.get(`/api/v1/accounting/journal-entries?limit=50&${params.toString()}`),
        api.get(`/api/v1/accounting/trial-balance?as_of_date=${encodeURIComponent(isoEnd)}`),
        api.get(`/api/v1/accounting/general-ledger?${ledgerParams.toString()}`),
        api.get(`/api/v1/accounting/income-statement?${params.toString()}`),
        api.get(`/api/v1/accounting/balance-sheet?as_of_date=${encodeURIComponent(isoEnd)}`),
        api.get(`/api/v1/accounting/reconciliation-report?${reconciliationParams.toString()}`),
      ])

      setData({
        summary: summaryResponse.data ?? EMPTY_DATA.summary,
        chartOfAccounts: chartResponse.data ?? [],
        journalEntries: journalResponse.data ?? EMPTY_DATA.journalEntries,
        trialBalance: trialBalanceResponse.data ?? EMPTY_DATA.trialBalance,
        generalLedger: ledgerResponse.data ?? EMPTY_DATA.generalLedger,
        incomeStatement: incomeResponse.data ?? EMPTY_DATA.incomeStatement,
        balanceSheet: balanceSheetResponse.data ?? EMPTY_DATA.balanceSheet,
        reconciliation: reconciliationResponse.data ?? EMPTY_DATA.reconciliation,
      })
    } catch (err: any) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refetch()
  }, [])

  if (loading && data.chartOfAccounts.length === 0 && data.journalEntries.items.length === 0) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-myhigh5-primary" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-96 flex-col items-center justify-center text-red-500">
        <AlertCircle className="mb-4 h-12 w-12" />
        <p>{t('admin.accounting.error_loading') || 'Error loading accounting data'}</p>
        <p className="text-sm text-gray-500">{error.message}</p>
        <Button onClick={refetch} className="mt-4" variant="outline">
          {t('admin.accounting.retry') || 'Retry'}
        </Button>
      </div>
    )
  }

  const summaryCards = [
    {
      title: 'Net Revenue',
      value: data.summary.net_revenue,
      icon: BarChart3,
      accent: 'text-green-600',
    },
    {
      title: 'Operating Income',
      value: data.summary.operating_income,
      icon: Scale,
      accent: 'text-indigo-600',
    },
    {
      title: 'Total Assets',
      value: data.summary.total_assets,
      icon: Wallet,
      accent: 'text-blue-600',
    },
    {
      title: 'Total Liabilities',
      value: data.summary.total_liabilities,
      icon: FileSpreadsheet,
      accent: 'text-amber-600',
    },
  ]

  const statementSections = [
    { title: 'Revenue', lines: data.incomeStatement.revenue },
    { title: 'Contra Revenue', lines: data.incomeStatement.contra_revenue },
    { title: 'Cost of Sales', lines: data.incomeStatement.cost_of_sales },
    { title: 'Operating Expenses', lines: data.incomeStatement.operating_expenses },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{t('admin.accounting.title') || 'Finance Workspace'}</h2>
          <p className="text-muted-foreground">
            Audit-ready accounting with period reporting, ledger drill-downs, and reconciliation.
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Period Start</label>
            <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Period End</label>
            <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">GL Account</label>
            <Input
              placeholder="e.g. 2060"
              value={ledgerAccountCode}
              onChange={(event) => setLedgerAccountCode(event.target.value)}
            />
          </div>
          <div className="flex items-end gap-2">
            <Button onClick={refetch} disabled={loading} className="gap-2">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarRange className="h-4 w-4" />
            Close Window
          </CardTitle>
          <CardDescription>
            {formatDateTime(data.summary.period_start, language, dateLocale)} to {formatDateTime(data.summary.period_end, language, dateLocale)}
          </CardDescription>
        </CardHeader>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map((card) => {
          const Icon = card.icon
          return (
            <Card key={card.title}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{card.title}</CardTitle>
                <Icon className={`h-4 w-4 ${card.accent}`} />
              </CardHeader>
              <CardContent>
                <div className={`text-2xl font-bold ${card.accent}`}>
                  {currencyFormatter.format(card.value)}
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader><CardTitle className="text-base">Deferred Membership</CardTitle></CardHeader>
          <CardContent className="text-xl font-semibold">{currencyFormatter.format(data.summary.deferred_membership_revenue)}</CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Deferred Service</CardTitle></CardHeader>
          <CardContent className="text-xl font-semibold">{currencyFormatter.format(data.summary.deferred_service_revenue)}</CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Prize Payable</CardTitle></CardHeader>
          <CardContent className="text-xl font-semibold">{currencyFormatter.format(data.summary.prize_payable)}</CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Commission Payable</CardTitle></CardHeader>
          <CardContent className="text-xl font-semibold">{currencyFormatter.format(data.summary.commission_payable)}</CardContent>
        </Card>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="flex h-auto flex-wrap">
          {FINANCE_LINKS.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>{tab.label}</TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="summary" className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Close KPIs</CardTitle>
                <CardDescription>Core balances finance would watch during the close.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex justify-between"><span>Wallet Liability</span><span className="font-mono">{currencyFormatter.format(data.summary.wallet_liability)}</span></div>
                <div className="flex justify-between"><span>Contra Revenue</span><span className="font-mono">{currencyFormatter.format(data.summary.total_contra_revenue)}</span></div>
                <div className="flex justify-between"><span>Cost of Sales</span><span className="font-mono">{currencyFormatter.format(data.summary.total_cost_of_sales)}</span></div>
                <div className="flex justify-between"><span>Journal Entries</span><span className="font-mono">{data.summary.journal_entry_count}</span></div>
                <div className="flex justify-between"><span>Latest Posting</span><span className="font-mono">{formatDateTime(data.summary.latest_entry_at, language, dateLocale)}</span></div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Statement Snapshot</CardTitle>
                <CardDescription>Current balance sheet and income statement totals.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex justify-between"><span>Total Equity</span><span className="font-mono">{currencyFormatter.format(data.summary.total_equity)}</span></div>
                <div className="flex justify-between"><span>Total Revenue</span><span className="font-mono">{currencyFormatter.format(data.summary.total_revenue)}</span></div>
                <div className="flex justify-between"><span>Net Revenue</span><span className="font-mono">{currencyFormatter.format(data.summary.net_revenue)}</span></div>
                <div className="flex justify-between"><span>Operating Expenses</span><span className="font-mono">{currencyFormatter.format(data.summary.total_expenses)}</span></div>
                <div className="flex justify-between"><span>Balance Sheet Balanced</span><Badge variant={data.balanceSheet.is_balanced ? 'default' : 'destructive'}>{data.balanceSheet.is_balanced ? 'Yes' : 'No'}</Badge></div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="coa" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Chart of Accounts</CardTitle>
              <CardDescription>Controller-grade chart with reporting metadata and balances for the selected period.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Code</TableHead>
                    <TableHead>Account</TableHead>
                    <TableHead>Section</TableHead>
                    <TableHead>Normal</TableHead>
                    <TableHead className="text-right">Opening</TableHead>
                    <TableHead className="text-right">Debit</TableHead>
                    <TableHead className="text-right">Credit</TableHead>
                    <TableHead className="text-right">Closing</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.chartOfAccounts.map((account) => (
                    <TableRow key={account.id}>
                      <TableCell className="font-mono font-medium">{account.account_code}</TableCell>
                      <TableCell>
                        <div className="font-medium">{account.account_name}</div>
                        <div className="text-xs text-gray-500">{account.report_group || account.description || ''}</div>
                      </TableCell>
                      <TableCell>{account.statement_section || '-'}</TableCell>
                      <TableCell>{account.normal_balance}</TableCell>
                      <TableCell className="text-right font-mono">{account.opening_balance.toFixed(2)}</TableCell>
                      <TableCell className="text-right font-mono">{account.total_debit.toFixed(2)}</TableCell>
                      <TableCell className="text-right font-mono">{account.total_credit.toFixed(2)}</TableCell>
                      <TableCell className="text-right font-mono">{account.balance.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="journal" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>General Journal</CardTitle>
              <CardDescription>Latest posted entries inside the selected reporting period.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Entry</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Debit</TableHead>
                    <TableHead className="text-right">Credit</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.journalEntries.items.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell>{formatDateTime(entry.entry_date, language, dateLocale)}</TableCell>
                      <TableCell className="font-mono text-xs">{entry.entry_number}</TableCell>
                      <TableCell>
                        <div className="font-medium">{entry.description}</div>
                        <div className="mt-1 text-xs text-gray-500">
                          {entry.event_type || 'posted'}
                          {entry.source_type && entry.source_id ? ` · ${entry.source_type}#${entry.source_id}` : ''}
                        </div>
                        <div className="mt-2 space-y-1 text-xs text-gray-500">
                          {entry.lines.map((line) => (
                            <div key={line.id} className="flex justify-between border-b border-gray-100 pb-1 last:border-0 dark:border-gray-800">
                              <span>{line.account_code} - {line.account_name}</span>
                              <span className="font-mono">
                                {line.debit_amount > 0 ? `D ${line.debit_amount.toFixed(2)}` : `C ${line.credit_amount.toFixed(2)}`}
                              </span>
                            </div>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell className="text-right font-mono">{entry.total_debit.toFixed(2)}</TableCell>
                      <TableCell className="text-right font-mono">{entry.total_credit.toFixed(2)}</TableCell>
                      <TableCell><Badge variant={entry.status === 'POSTED' ? 'default' : 'secondary'}>{entry.status}</Badge></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="trial-balance" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Trial Balance</CardTitle>
              <CardDescription>
                {data.trialBalance.is_balanced ? 'Debits and credits balance as of the selected date.' : 'Trial balance is out of balance.'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-lg border p-4">
                  <div className="text-sm text-muted-foreground">As Of</div>
                  <div className="text-lg font-semibold">{formatDateTime(data.trialBalance.as_of_date ?? null, language, dateLocale)}</div>
                </div>
                <div className="rounded-lg border p-4">
                  <div className="text-sm text-muted-foreground">Total Debits</div>
                  <div className="text-lg font-semibold">{currencyFormatter.format(data.trialBalance.total_debits)}</div>
                </div>
                <div className="rounded-lg border p-4">
                  <div className="text-sm text-muted-foreground">Total Credits</div>
                  <div className="text-lg font-semibold">{currencyFormatter.format(data.trialBalance.total_credits)}</div>
                </div>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Code</TableHead>
                    <TableHead>Account</TableHead>
                    <TableHead className="text-right">Debit</TableHead>
                    <TableHead className="text-right">Credit</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.trialBalance.accounts
                    .filter((account) => account.total_debit !== 0 || account.total_credit !== 0)
                    .map((account) => (
                      <TableRow key={account.id}>
                        <TableCell className="font-mono">{account.account_code}</TableCell>
                        <TableCell>{account.account_name}</TableCell>
                        <TableCell className="text-right font-mono">{account.total_debit.toFixed(2)}</TableCell>
                        <TableCell className="text-right font-mono">{account.total_credit.toFixed(2)}</TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="general-ledger" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BookOpen className="h-4 w-4" />
                General Ledger
              </CardTitle>
              <CardDescription>Running balances by account within the selected period.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-lg border p-4">
                  <div className="text-sm text-muted-foreground">Account Filter</div>
                  <div className="text-lg font-semibold">{data.generalLedger.account_code || 'All accounts'}</div>
                </div>
                <div className="rounded-lg border p-4">
                  <div className="text-sm text-muted-foreground">Opening Balance</div>
                  <div className="text-lg font-semibold">{currencyFormatter.format(data.generalLedger.opening_balance)}</div>
                </div>
                <div className="rounded-lg border p-4">
                  <div className="text-sm text-muted-foreground">Closing Balance</div>
                  <div className="text-lg font-semibold">{currencyFormatter.format(data.generalLedger.closing_balance)}</div>
                </div>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Entry</TableHead>
                    <TableHead>Account</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Debit</TableHead>
                    <TableHead className="text-right">Credit</TableHead>
                    <TableHead className="text-right">Running</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.generalLedger.lines.map((line) => (
                    <TableRow key={`${line.entry_id}-${line.account_code}-${line.debit_amount}-${line.credit_amount}`}>
                      <TableCell>{formatDateTime(line.entry_date, language, dateLocale)}</TableCell>
                      <TableCell className="font-mono text-xs">{line.entry_number}</TableCell>
                      <TableCell className="font-mono">{line.account_code}</TableCell>
                      <TableCell>{line.description || `${line.account_name}`}</TableCell>
                      <TableCell className="text-right font-mono">{line.debit_amount.toFixed(2)}</TableCell>
                      <TableCell className="text-right font-mono">{line.credit_amount.toFixed(2)}</TableCell>
                      <TableCell className="text-right font-mono">{line.running_balance.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="statements" className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Income Statement</CardTitle>
                <CardDescription>
                  {formatDateTime(data.incomeStatement.start_date, language, dateLocale)} to {formatDateTime(data.incomeStatement.end_date, language, dateLocale)}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {statementSections.map((section) => (
                  <div key={section.title}>
                    <div className="mb-2 text-sm font-semibold text-muted-foreground">{section.title}</div>
                    <div className="space-y-2">
                      {section.lines.length ? section.lines.map((line) => (
                        <div key={`${section.title}-${line.account_code}`} className="flex justify-between text-sm">
                          <span>{line.account_code} - {line.account_name}</span>
                          <span className="font-mono">{currencyFormatter.format(line.amount)}</span>
                        </div>
                      )) : <div className="text-sm text-muted-foreground">No activity</div>}
                    </div>
                  </div>
                ))}
                <div className="border-t pt-3 text-sm">
                  <div className="flex justify-between"><span>Net Revenue</span><span className="font-mono">{currencyFormatter.format(data.incomeStatement.net_revenue)}</span></div>
                  <div className="flex justify-between"><span>Gross Profit</span><span className="font-mono">{currencyFormatter.format(data.incomeStatement.gross_profit)}</span></div>
                  <div className="flex justify-between font-semibold"><span>Operating Income</span><span className="font-mono">{currencyFormatter.format(data.incomeStatement.operating_income)}</span></div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Balance Sheet</CardTitle>
                <CardDescription>As of {formatDateTime(data.balanceSheet.as_of_date, language, dateLocale)}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {[
                  { title: 'Assets', lines: data.balanceSheet.assets },
                  { title: 'Liabilities', lines: data.balanceSheet.liabilities },
                  { title: 'Equity', lines: data.balanceSheet.equity },
                ].map((section) => (
                  <div key={section.title}>
                    <div className="mb-2 text-sm font-semibold text-muted-foreground">{section.title}</div>
                    <div className="space-y-2">
                      {section.lines.length ? section.lines.map((line) => (
                        <div key={`${section.title}-${line.account_code}`} className="flex justify-between text-sm">
                          <span>{line.account_code} - {line.account_name}</span>
                          <span className="font-mono">{currencyFormatter.format(line.amount)}</span>
                        </div>
                      )) : <div className="text-sm text-muted-foreground">No balance</div>}
                    </div>
                  </div>
                ))}
                <div className="border-t pt-3 text-sm">
                  <div className="flex justify-between"><span>Total Assets</span><span className="font-mono">{currencyFormatter.format(data.balanceSheet.total_assets)}</span></div>
                  <div className="flex justify-between"><span>Total Liabilities</span><span className="font-mono">{currencyFormatter.format(data.balanceSheet.total_liabilities)}</span></div>
                  <div className="flex justify-between"><span>Total Equity</span><span className="font-mono">{currencyFormatter.format(data.balanceSheet.total_equity)}</span></div>
                  <div className="mt-2 flex justify-between font-semibold">
                    <span>Status</span>
                    <Badge variant={data.balanceSheet.is_balanced ? 'default' : 'destructive'}>
                      {data.balanceSheet.is_balanced ? 'Balanced' : 'Out of balance'}
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="reconciliation" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Reconciliation</CardTitle>
              <CardDescription>Grouped source-to-ledger traceability across operational events.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {['all', 'deposit', 'transaction', 'affiliate_commission'].map((option) => (
                  <Button
                    key={option}
                    size="sm"
                    variant={reconciliationFilter === option ? 'default' : 'outline'}
                    onClick={() => setReconciliationFilter(option)}
                  >
                    {option}
                  </Button>
                ))}
                <Button size="sm" variant="outline" onClick={refetch}>Apply Filter</Button>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Source</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Entries</TableHead>
                    <TableHead className="text-right">Debit</TableHead>
                    <TableHead className="text-right">Credit</TableHead>
                    <TableHead>Latest</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.reconciliation.items.map((item) => (
                    <TableRow key={`${item.source_type}-${item.source_id}`}>
                      <TableCell className="font-mono">{item.source_type}#{item.source_id}</TableCell>
                      <TableCell>
                        <div>{item.description || '-'}</div>
                        <div className="text-xs text-gray-500">{item.reference_number || ''}</div>
                      </TableCell>
                      <TableCell className="text-right font-mono">{item.entry_count}</TableCell>
                      <TableCell className="text-right font-mono">{item.total_debit.toFixed(2)}</TableCell>
                      <TableCell className="text-right font-mono">{item.total_credit.toFixed(2)}</TableCell>
                      <TableCell>{formatDateTime(item.latest_entry_at ?? null, language, dateLocale)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
