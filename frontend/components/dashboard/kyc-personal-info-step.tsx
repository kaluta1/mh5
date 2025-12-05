'use client'

import { useLanguage } from '@/contexts/language-context'
import { countries } from '@/lib/countries'
import { User } from 'lucide-react'

interface PersonalInfoData {
  firstName: string
  lastName: string
  dateOfBirth: string
  nationality: string
  address: string
}

interface KYCPersonalInfoStepProps {
  data: PersonalInfoData
  onChange: (field: keyof PersonalInfoData, value: string) => void
  errors?: { [key: string]: string }
}

export function KYCPersonalInfoStep({ data, onChange, errors = {} }: KYCPersonalInfoStepProps) {
  const { t } = useLanguage()

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <User className="w-6 h-6 text-myfav-primary" />
          {t('kyc.personal_info')}
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* First Name */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            {t('kyc.first_name')}
          </label>
          <input
            type="text"
            value={data.firstName}
            onChange={(e) => onChange('firstName', e.target.value)}
            placeholder={t('kyc.first_name_placeholder')}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            required
          />
        </div>

        {/* Last Name */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            {t('kyc.last_name')}
          </label>
          <input
            type="text"
            value={data.lastName}
            onChange={(e) => onChange('lastName', e.target.value)}
            placeholder={t('kyc.last_name_placeholder')}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            required
          />
        </div>

        {/* Date of Birth */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            {t('kyc.date_of_birth')}
          </label>
          <input
            type="date"
            value={data.dateOfBirth}
            onChange={(e) => onChange('dateOfBirth', e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            required
          />
        </div>

        {/* Nationality */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            {t('kyc.nationality')}
          </label>
          <select
            value={data.nationality}
            onChange={(e) => onChange('nationality', e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            required
          >
            <option value="">{t('kyc.nationality_placeholder')}</option>
            {countries.map((country) => (
              <option key={country.code} value={country.name}>
                {country.name}
              </option>
            ))}
          </select>
        </div>

        {/* Address */}
        <div className="md:col-span-2">
          <label className="block text-sm font-semibold text-gray-900 dark:text-white mb-2">
            {t('kyc.address')}
          </label>
          <input
            type="text"
            value={data.address}
            onChange={(e) => onChange('address', e.target.value)}
            placeholder={t('kyc.address_placeholder')}
            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-myfav-primary"
            required
          />
        </div>
      </div>
    </div>
  )
}
