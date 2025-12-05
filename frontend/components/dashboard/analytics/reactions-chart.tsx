"use client"

import * as React from "react"
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { useLanguage } from '@/contexts/language-context'

interface ReactionData {
  name: string
  value: number
  color: string
  [key: string]: string | number
}

interface ReactionsChartProps {
  data: ReactionData[]
  title?: string
  subtitle?: string
}

export function ReactionsChart({ 
  data, 
  title,
  subtitle
}: ReactionsChartProps) {
  const { t } = useLanguage()
  
  const chartTitle = title || t('dashboard.analytics.reactions_distribution') || 'Reactions'
  const chartSubtitle = subtitle || t('dashboard.analytics.reactions_distribution_desc') || 'Distribution by type'

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl p-6 border border-gray-100 dark:border-gray-800">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{chartTitle}</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">{chartSubtitle}</p>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data as unknown as Array<{[key: string]: string | number}>}
              cx="50%"
              cy="50%"
              innerRadius={50}
              outerRadius={80}
              paddingAngle={4}
              dataKey="value"
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip 
              contentStyle={{ 
                backgroundColor: '#1f2937', 
                border: 'none', 
                borderRadius: '8px',
                color: '#fff'
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-4">
        {data.map((item, index) => (
          <div key={index} className="flex items-center gap-2">
            <div 
              className="w-3 h-3 rounded-full" 
              style={{ backgroundColor: item.color }} 
            />
            <span className="text-xs text-gray-600 dark:text-gray-400">{item.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
