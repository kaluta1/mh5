'use client'

import { useLanguage } from '@/contexts/language-context'
import { Percent, Construction } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function CommissionSettingsPage() {
  const { t } = useLanguage()

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary/80 to-myhigh5-secondary dark:from-myhigh5-primary/20 dark:via-myhigh5-primary/10 dark:to-myhigh5-secondary/10 rounded-xl p-8 border border-myhigh5-primary/30 dark:border-myhigh5-primary/20 shadow-lg">
        <div className="flex items-center gap-3 mb-3">
          <Percent className="h-8 w-8 text-white dark:text-myhigh5-secondary" />
          <h1 className="text-4xl font-bold text-white dark:text-white">
            {t('admin.nav.commission_settings') || 'Commission Settings'}
          </h1>
        </div>
        <p className="text-myhigh5-primary/90 dark:text-myhigh5-secondary/80 font-medium">
          {t('admin.commission_settings.subtitle') || 'Configure commission rules and rates'}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Construction className="h-5 w-5" />
            {t('common.coming_soon') || 'Bientôt disponible'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-gray-600 dark:text-gray-400">
            {t('admin.commission_settings.coming_soon') || 'This section is under development. Commission settings will be available soon.'}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
