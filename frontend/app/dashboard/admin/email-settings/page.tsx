'use client'

import AdminEmailSettings from '@/components/admin/admin-email-settings'

export default function EmailSettingsPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">Email Settings</h1>
        <p className="text-gray-600 dark:text-gray-400 mt-2">
          Email system status, the Resend provider, the switch of every email event and the delivery log. Secrets are never shown.
        </p>
      </div>
      <AdminEmailSettings />
    </div>
  )
}
