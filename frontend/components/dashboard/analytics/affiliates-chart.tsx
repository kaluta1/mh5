"use client"

import * as React from "react"
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, 
  CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import { useLanguage } from '@/contexts/language-context'

interface AffiliatesData {
  month: string
  directs: number
  total: number
  commissions: number
}

interface AffiliatesGrowthChartProps {
  data: AffiliatesData[]
  title?: string
  subtitle?: string
}

export function AffiliatesGrowthChart({ 
  data, 
  title,
  subtitle
}: AffiliatesGrowthChartProps) {
  const { t } = useLanguage()
  
  const chartTitle = title || t('dashboard.analytics.network_growth') || 'Network Growth'
  const chartSubtitle = subtitle || t('dashboard.analytics.network_growth_desc') || 'Evolution of your affiliates'
  const directsLabel = t('dashboard.analytics.direct_affiliates') || 'Direct Affiliates'
  const totalLabel = t('dashboard.analytics.total_network') || 'Total Network'

  // Traduire les mois
  const translateMonth = (month: string) => {
    const translations: Record<string, string> = {
      'Jan': t('common.months.jan') || 'Jan',
      'Feb': t('common.months.feb') || 'Fév',
      'Mar': t('common.months.mar') || 'Mar',
      'Apr': t('common.months.apr') || 'Avr',
      'May': t('common.months.may') || 'Mai',
      'Jun': t('common.months.jun') || 'Juin',
      'Jul': t('common.months.jul') || 'Juil',
      'Aug': t('common.months.aug') || 'Août',
      'Sep': t('common.months.sep') || 'Sep',
      'Oct': t('common.months.oct') || 'Oct',
      'Nov': t('common.months.nov') || 'Nov',
      'Dec': t('common.months.dec') || 'Déc',
      'Fév': t('common.months.feb') || 'Fév',
      'Avr': t('common.months.apr') || 'Avr',
      'Mai': t('common.months.may') || 'Mai',
      'Juin': t('common.months.jun') || 'Juin',
      'Juil': t('common.months.jul') || 'Juil',
      'Août': t('common.months.aug') || 'Août',
      'Déc': t('common.months.dec') || 'Déc'
    }
    return translations[month] || month
  }

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl p-6 border border-gray-100 dark:border-gray-800">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{chartTitle}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">{chartSubtitle}</p>
        </div>
      </div>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="colorDirects" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} tickFormatter={translateMonth} />
            <YAxis tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#1f2937', 
                border: 'none', 
                borderRadius: '8px',
                color: '#fff'
              }} 
            />
            <Legend />
            <Area 
              type="monotone" 
              dataKey="directs" 
              name={directsLabel}
              stroke="#6366f1" 
              fillOpacity={1} 
              fill="url(#colorDirects)" 
              strokeWidth={2} 
            />
            <Area 
              type="monotone" 
              dataKey="total" 
              name={totalLabel}
              stroke="#06b6d4" 
              fillOpacity={1} 
              fill="url(#colorTotal)" 
              strokeWidth={2} 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

interface CommissionsChartProps {
  data: AffiliatesData[]
  title?: string
  subtitle?: string
}

export function CommissionsChart({ 
  data, 
  title,
  subtitle
}: CommissionsChartProps) {
  const { t } = useLanguage()
  
  const chartTitle = title || t('dashboard.analytics.monthly_commissions') || 'Monthly Commissions'
  const chartSubtitle = subtitle || t('dashboard.analytics.monthly_commissions_desc') || 'Revenue from your network'
  const commissionsLabel = t('dashboard.analytics.commissions') || 'Commissions'

  // Traduire les mois
  const translateMonth = (month: string) => {
    const translations: Record<string, string> = {
      'Jan': t('common.months.jan') || 'Jan',
      'Feb': t('common.months.feb') || 'Fév',
      'Mar': t('common.months.mar') || 'Mar',
      'Apr': t('common.months.apr') || 'Avr',
      'May': t('common.months.may') || 'Mai',
      'Jun': t('common.months.jun') || 'Juin',
      'Jul': t('common.months.jul') || 'Juil',
      'Aug': t('common.months.aug') || 'Août',
      'Sep': t('common.months.sep') || 'Sep',
      'Oct': t('common.months.oct') || 'Oct',
      'Nov': t('common.months.nov') || 'Nov',
      'Dec': t('common.months.dec') || 'Déc',
      'Fév': t('common.months.feb') || 'Fév',
      'Avr': t('common.months.apr') || 'Avr',
      'Mai': t('common.months.may') || 'Mai',
      'Juin': t('common.months.jun') || 'Juin',
      'Juil': t('common.months.jul') || 'Juil',
      'Août': t('common.months.aug') || 'Août',
      'Déc': t('common.months.dec') || 'Déc'
    }
    return translations[month] || month
  }

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl p-6 border border-gray-100 dark:border-gray-800">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{chartTitle}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">{chartSubtitle}</p>
        </div>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} tickFormatter={translateMonth} />
            <YAxis 
              tick={{ fontSize: 12 }} 
              tickLine={false} 
              axisLine={false} 
              tickFormatter={(value) => `$${value}`} 
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#1f2937', 
                border: 'none', 
                borderRadius: '8px',
                color: '#fff'
              }}
              formatter={(value) => [`$${value}`, commissionsLabel]}
            />
            <Bar 
              dataKey="commissions" 
              name={commissionsLabel}
              fill="#10b981" 
              radius={[6, 6, 0, 0]} 
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
