'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { TrendingUp, Users } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'
import { cn } from '@/lib/utils'

interface UserProgressData {
  date: string
  total: number
  active: number
  new: number
}

type PeriodType = 'today' | 'yesterday' | 'week' | 'month' | 'year'

interface UserProgressChartProps {
  data: UserProgressData[]
  title?: string
  period?: PeriodType
  onPeriodChange?: (period: PeriodType) => void
}

export function UserProgressChart({ data, title, period = 'week', onPeriodChange }: UserProgressChartProps) {
  const { t } = useLanguage()
  const chartTitle = title || t('admin.dashboard.user_progress')
  
  const periods: { value: PeriodType; label: string }[] = [
    { value: 'today', label: t('admin.dashboard.periods.today') || 'Aujourd\'hui' },
    { value: 'yesterday', label: t('admin.dashboard.periods.yesterday') || 'Hier' },
    { value: 'week', label: t('admin.dashboard.periods.week') || 'Semaine' },
    { value: 'month', label: t('admin.dashboard.periods.month') || 'Mois' },
    { value: 'year', label: t('admin.dashboard.periods.year') || 'Année' }
  ]

  return (
    <Card className="border-gray-200 dark:border-gray-700">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-900/50 flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <CardTitle className="text-lg font-semibold text-gray-900 dark:text-white">
              {chartTitle}
            </CardTitle>
          </div>
          {onPeriodChange && (
            <div className="flex items-center gap-2">
              {periods.map((p) => (
                <Button
                  key={p.value}
                  variant={period === p.value ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => onPeriodChange(p.value)}
                  className={cn(
                    'h-8 px-3 text-xs',
                    period === p.value
                      ? 'bg-blue-600 hover:bg-blue-700 text-white'
                      : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                  )}
                >
                  {p.label}
                </Button>
              ))}
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="colorActive" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis 
              dataKey="date" 
              className="text-xs text-gray-600 dark:text-gray-400"
              tick={{ fill: 'currentColor' }}
            />
            <YAxis 
              className="text-xs text-gray-600 dark:text-gray-400"
              tick={{ fill: 'currentColor' }}
            />
            <Tooltip 
              contentStyle={{
                backgroundColor: 'var(--background)',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                color: 'var(--foreground)'
              }}
            />
            <Legend 
              wrapperStyle={{ paddingTop: '20px' }}
              iconType="circle"
            />
            <Area 
              type="monotone" 
              dataKey="total" 
              stroke="#3b82f6" 
              fillOpacity={1} 
              fill="url(#colorTotal)"
              name={t('admin.dashboard.chart_labels.total_users')}
              strokeWidth={2}
            />
            <Area 
              type="monotone" 
              dataKey="active" 
              stroke="#10b981" 
              fillOpacity={1} 
              fill="url(#colorActive)"
              name={t('admin.dashboard.chart_labels.active_users')}
              strokeWidth={2}
            />
            <Line 
              type="monotone" 
              dataKey="new" 
              stroke="#f59e0b" 
              strokeWidth={2}
              dot={{ fill: '#f59e0b', r: 4 }}
              name={t('admin.dashboard.chart_labels.new_users')}
            />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}

