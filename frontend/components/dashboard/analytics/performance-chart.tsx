"use client"

import * as React from "react"
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, 
  Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import { useLanguage } from '@/contexts/language-context'

interface ContestPerformance {
  name: string
  votes: number
  comments: number
  views: number
  likes: number
}

interface PerformanceChartProps {
  data: ContestPerformance[]
  title?: string
  subtitle?: string
}

export function PerformanceChart({ 
  data, 
  title,
  subtitle
}: PerformanceChartProps) {
  const { t } = useLanguage()
  
  const chartTitle = title || t('dashboard.analytics.contest_performance') || 'Contest Performance'
  const chartSubtitle = subtitle || t('dashboard.analytics.contest_performance_desc') || 'Votes and engagement'
  const votesLabel = t('dashboard.analytics.total_votes') || 'Votes'
  const likesLabel = t('dashboard.analytics.likes') || 'Likes'
  const commentsLabel = t('dashboard.analytics.comments') || 'Comments'

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl p-6 border border-gray-100 dark:border-gray-800">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{chartTitle}</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">{chartSubtitle}</p>
        </div>
      </div>
      <div className="h-80 overflow-x-auto">
        <div className="min-w-[500px] h-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} barGap={8}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis 
              dataKey="name" 
              tick={{ fontSize: 12 }} 
              tickLine={false} 
              axisLine={false} 
            />
            <YAxis 
              tick={{ fontSize: 12 }} 
              tickLine={false} 
              axisLine={false} 
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#1f2937', 
                border: 'none', 
                borderRadius: '8px',
                color: '#fff'
              }} 
            />
            <Legend />
            <Bar dataKey="votes" name={votesLabel} fill="#3b82f6" radius={[4, 4, 0, 0]} />
            <Bar dataKey="likes" name={likesLabel} fill="#10b981" radius={[4, 4, 0, 0]} />
            <Bar dataKey="comments" name={commentsLabel} fill="#f59e0b" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
