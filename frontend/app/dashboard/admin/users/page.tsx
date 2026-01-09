'use client'

import { useLanguage } from '@/contexts/language-context'
import AdminUsers from '@/components/admin/admin-users'
import { Users } from 'lucide-react'

export default function UsersPage() {
  const { t } = useLanguage()

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-br from-myhigh5-primary via-myhigh5-primary/80 to-myhigh5-secondary dark:from-myhigh5-primary/20 dark:via-myhigh5-primary/10 dark:to-myhigh5-secondary/10 rounded-xl p-8 border border-myhigh5-primary/30 dark:border-myhigh5-primary/20 shadow-lg">
        <div className="flex items-center gap-3 mb-3">
          <Users className="h-8 w-8 text-white dark:text-myhigh5-secondary" />
          <h1 className="text-4xl font-bold text-white dark:text-white">
            {t('admin.users.title') || 'Gestion des Utilisateurs'}
          </h1>
        </div>
        <p className="text-myhigh5-primary/90 dark:text-myhigh5-secondary/80 font-medium">
          {t('admin.users.description') || 'Gérez les rôles et les permissions des utilisateurs'}
        </p>
      </div>

      {/* Admin Users Component */}
      <AdminUsers />
    </div>
  )
}
