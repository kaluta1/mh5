"use client"

import * as React from "react"
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, 
  Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import { useLanguage } from '@/contexts/language-context'

interface ActivityData {
  day: string
  votes: number
  views: number
}

interface ActivityChartProps {
  data: ActivityData[]
  title?: string
  subtitle?: string
}

export function ActivityChart({ 
  data, 
  title,
  subtitle
}: ActivityChartProps) {
  const { t } = useLanguage()
  
  const chartTitle = title || t('dashboard.analytics.weekly_activity') || 'Weekly Activity'
  const chartSubtitle = subtitle || t('dashboard.analytics.weekly_activity_desc') || 'Votes and views this week'
  const votesLabel = t('dashboard.analytics.total_votes') || 'Votes'
  const viewsLabel = t('dashboard.analytics.total_views') || 'Views'

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
          <AreaChart data={data}>
            <defs>
              <linearGradient id="colorVotes" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="colorViews" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="day" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
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
              dataKey="votes" 
              name={votesLabel}
              stroke="#3b82f6" 
              fillOpacity={1} 
              fill="url(#colorVotes)" 
              strokeWidth={2} 
            />
            <Area 
              type="monotone" 
              dataKey="views" 
              name={viewsLabel}
              stroke="#10b981" 
              fillOpacity={1} 
              fill="url(#colorViews)" 
              strokeWidth={2} 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
