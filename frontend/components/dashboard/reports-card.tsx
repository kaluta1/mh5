'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FileText, Download, BarChart3, TrendingUp, Calendar } from 'lucide-react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { useLanguage } from '@/contexts/language-context'

interface Report {
  id: string
  title: string
  type: 'financial' | 'users' | 'contests' | 'votes'
  date: string
  downloadUrl?: string
}

interface ReportsCardProps {
  reports?: Report[]
  onGenerateReport?: (type: string) => void
}

export function ReportsCard({ reports = [], onGenerateReport }: ReportsCardProps) {
  const { t } = useLanguage()

  const reportTypes = [
    {
      type: 'financial',
      label: t('admin.dashboard.reports.financial_report'),
      icon: BarChart3,
      color: 'from-green-500 to-emerald-600',
      description: t('admin.dashboard.reports.financial_description')
    },
    {
      type: 'users',
      label: t('admin.dashboard.reports.users_report'),
      icon: TrendingUp,
      color: 'from-blue-500 to-cyan-600',
      description: t('admin.dashboard.reports.users_description')
    },
    {
      type: 'contests',
      label: t('admin.dashboard.reports.contests_report'),
      icon: Calendar,
      color: 'from-purple-500 to-pink-600',
      description: t('admin.dashboard.reports.contests_description')
    },
    {
      type: 'votes',
      label: t('admin.dashboard.reports.votes_report'),
      icon: FileText,
      color: 'from-orange-500 to-red-600',
      description: t('admin.dashboard.reports.votes_description')
    }
  ]
  return (
    <Card className="border-gray-200 dark:border-gray-700">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <div>
              <CardTitle className="text-xl font-bold text-gray-900 dark:text-white">
                {t('admin.dashboard.reports.title')}
              </CardTitle>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {t('admin.dashboard.reports.description')}
              </p>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {reportTypes.map((reportType) => {
            const Icon = reportType.icon
            return (
              <button
                key={reportType.type}
                onClick={() => onGenerateReport?.(reportType.type)}
                className="group relative p-4 rounded-xl border-2 border-gray-200 dark:border-gray-700 hover:border-myfav-primary/50 dark:hover:border-myfav-blue-400/50 transition-all duration-300 hover:shadow-lg bg-white dark:bg-gray-800 text-left"
              >
                <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${reportType.color} rounded-t-xl`} />
                <div className="flex items-start gap-3 mt-2">
                  <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${reportType.color} flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform`}>
                    <Icon className="w-5 h-5 text-white" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h4 className="font-semibold text-gray-900 dark:text-white group-hover:text-myfav-primary dark:group-hover:text-myfav-blue-400 transition-colors">
                      {reportType.label}
                    </h4>
                    <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                      {reportType.description}
                    </p>
                  </div>
                </div>
              </button>
            )
          })}
        </div>

        {reports.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">
              {t('admin.dashboard.reports.recent_reports')}
            </h4>
            {reports.slice(0, 3).map((report) => (
              <div
                key={report.id}
                className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <FileText className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {report.title}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {report.date}
                    </p>
                  </div>
                </div>
                {report.downloadUrl && (
                  <Button
                    variant="ghost"
                    size="sm"
                    asChild
                    className="h-8 w-8 p-0"
                  >
                    <Link href={report.downloadUrl}>
                      <Download className="w-4 h-4" />
                    </Link>
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

