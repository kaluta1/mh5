'use client'

import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { X } from 'lucide-react'
import { useLanguage } from '@/contexts/language-context'

interface RoundDialogProps {
    isOpen: boolean
    onClose: () => void
    onSave: (data: any) => Promise<void>
    initialData?: any
    contests: any[]
}

export function RoundDialog({
    isOpen,
    onClose,
    onSave,
    initialData,
    contests
}: RoundDialogProps) {
    const { t } = useLanguage()
    const [formData, setFormData] = useState({
        contest_id: '',
        name: '',
        status: 'upcoming',
        submission_start_date: '',
        submission_end_date: '',
        voting_start_date: '',
        voting_end_date: '',
        city_season_start_date: '',
        city_season_end_date: '',
        country_season_start_date: '',
        country_season_end_date: '',
        regional_start_date: '',
        regional_end_date: '',
        continental_start_date: '',
        continental_end_date: '',
        global_start_date: '',
        global_end_date: ''
    })
    const [isSubmitting, setIsSubmitting] = useState(false)

    useEffect(() => {
        if (initialData) {
            const formatDateForInput = (dateStr?: string) => {
                if (!dateStr) return ''
                return dateStr.split('T')[0]
            }
            setFormData({
                contest_id: initialData.contest_id?.toString() || '',
                name: initialData.name,
                status: initialData.status || 'upcoming',
                submission_start_date: formatDateForInput(initialData.submission_start_date),
                submission_end_date: formatDateForInput(initialData.submission_end_date),
                voting_start_date: formatDateForInput(initialData.voting_start_date),
                voting_end_date: formatDateForInput(initialData.voting_end_date),
                city_season_start_date: formatDateForInput(initialData.city_season_start_date),
                city_season_end_date: formatDateForInput(initialData.city_season_end_date),
                country_season_start_date: formatDateForInput(initialData.country_season_start_date),
                country_season_end_date: formatDateForInput(initialData.country_season_end_date),
                regional_start_date: formatDateForInput(initialData.regional_start_date),
                regional_end_date: formatDateForInput(initialData.regional_end_date),
                continental_start_date: formatDateForInput(initialData.continental_start_date),
                continental_end_date: formatDateForInput(initialData.continental_end_date),
                global_start_date: formatDateForInput(initialData.global_start_date),
                global_end_date: formatDateForInput(initialData.global_end_date),
            })
        } else {
            setFormData({
                contest_id: '',
                name: '',
                status: 'upcoming',
                submission_start_date: '',
                submission_end_date: '',
                voting_start_date: '',
                voting_end_date: '',
                city_season_start_date: '',
                city_season_end_date: '',
                country_season_start_date: '',
                country_season_end_date: '',
                regional_start_date: '',
                regional_end_date: '',
                continental_start_date: '',
                continental_end_date: '',
                global_start_date: '',
                global_end_date: ''
            })
        }
    }, [initialData])

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        setIsSubmitting(true)
        try {
            // Clean up empty dates to prevent validation error
            const dataToSave = { ...formData }
            const dateFields = [
                'submission_start_date', 'submission_end_date', 'voting_start_date', 'voting_end_date',
                'city_season_start_date', 'city_season_end_date', 'country_season_start_date', 'country_season_end_date',
                'regional_start_date', 'regional_end_date', 'continental_start_date', 'continental_end_date',
                'global_start_date', 'global_end_date'
            ]

            dateFields.forEach(field => {
                // @ts-ignore
                if (dataToSave[field] === '') {
                    // @ts-ignore
                    dataToSave[field] = null
                }
            })

            await onSave(dataToSave)
            onClose()
        } catch (error) {
            console.error(error)
        } finally {
            setIsSubmitting(false)
        }
    }

    if (!isOpen) return null

    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto dark:bg-gray-800">
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4 border-b dark:border-gray-700">
                    <CardTitle className="text-xl">
                        {initialData ? t('admin.rounds.edit') || 'Modifier un Round' : t('admin.rounds.create') || 'Nouveau Round'}
                    </CardTitle>
                    <button
                        onClick={onClose}
                        className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                    >
                        <X className="h-5 w-5" />
                    </button>
                </CardHeader>
                <CardContent className="pt-6">
                    <form onSubmit={handleSubmit} className="space-y-6">
                        <div className="grid md:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                    {t('admin.rounds.contest') || 'Concours'}
                                </label>
                                <Select
                                    value={formData.contest_id}
                                    onValueChange={(value) => setFormData({ ...formData, contest_id: value })}
                                    disabled={!!initialData} // Cannot change contest when editing
                                >
                                    <SelectTrigger className="dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                                        <SelectValue placeholder={t('admin.rounds.select_contest') || 'Choisir un concours'} />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {contests.map((contest) => (
                                            <SelectItem key={contest.id} value={contest.id.toString()}>
                                                {contest.name}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium mb-1 dark:text-gray-200">
                                    {t('admin.rounds.name') || 'Nom du Round'}
                                </label>
                                <Input
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    placeholder="ex: Round Janvier 2026"
                                    className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                    required
                                />
                            </div>
                        </div>

                        {/* Dates */}
                        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-800">
                            <h4 className="font-semibold text-sm text-blue-900 dark:text-blue-200 mb-4">📅 Planning</h4>
                            <div className="space-y-4">
                                {/* Upload & Voting */}
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                                            Uploads Start
                                        </label>
                                        <Input
                                            type="date"
                                            value={formData.submission_start_date}
                                            onChange={(e) => setFormData({ ...formData, submission_start_date: e.target.value })}
                                            className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                                            Uploads End
                                        </label>
                                        <Input
                                            type="date"
                                            value={formData.submission_end_date}
                                            onChange={(e) => setFormData({ ...formData, submission_end_date: e.target.value })}
                                            className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                                            Voting Start
                                        </label>
                                        <Input
                                            type="date"
                                            value={formData.voting_start_date}
                                            onChange={(e) => setFormData({ ...formData, voting_start_date: e.target.value })}
                                            className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-medium text-blue-700 dark:text-blue-300 mb-2">
                                            Voting End
                                        </label>
                                        <Input
                                            type="date"
                                            value={formData.voting_end_date}
                                            onChange={(e) => setFormData({ ...formData, voting_end_date: e.target.value })}
                                            className="dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                                        />
                                    </div>
                                </div>

                                {/* Season Dates */}
                                <div className="border-t border-blue-200 dark:border-blue-800 pt-4 space-y-4">
                                    {/* City Season */}
                                    <div className="grid grid-cols-3 gap-2 items-center">
                                        <span className="text-xs font-semibold text-blue-900 dark:text-blue-200">{t('admin.rounds.city_season') || 'Saison Ville'}</span>
                                        <div className="col-span-2 grid grid-cols-2 gap-2">
                                            <div>
                                                <label className="block text-[10px] mb-1 opacity-70">{t('admin.rounds.start_date') || 'Début'}</label>
                                                <Input type="date" value={formData.city_season_start_date} onChange={(e) => setFormData({ ...formData, city_season_start_date: e.target.value })} className="h-8 dark:bg-gray-700" />
                                            </div>
                                            <div>
                                                <label className="block text-[10px] mb-1 opacity-70">{t('admin.rounds.end_date') || 'Fin'}</label>
                                                <Input type="date" value={formData.city_season_end_date} onChange={(e) => setFormData({ ...formData, city_season_end_date: e.target.value })} className="h-8 dark:bg-gray-700" />
                                            </div>
                                        </div>
                                    </div>

                                    {/* Country Season */}
                                    <div className="grid grid-cols-3 gap-2 items-center">
                                        <span className="text-xs font-semibold text-blue-900 dark:text-blue-200">{t('admin.rounds.country_season') || 'Saison Pays'}</span>
                                        <div className="col-span-2 grid grid-cols-2 gap-2">
                                            <div>
                                                <label className="block text-[10px] mb-1 opacity-70">{t('admin.rounds.start_date') || 'Début'}</label>
                                                <Input type="date" value={formData.country_season_start_date} onChange={(e) => setFormData({ ...formData, country_season_start_date: e.target.value })} className="h-8 dark:bg-gray-700" />
                                            </div>
                                            <div>
                                                <label className="block text-[10px] mb-1 opacity-70">{t('admin.rounds.end_date') || 'Fin'}</label>
                                                <Input type="date" value={formData.country_season_end_date} onChange={(e) => setFormData({ ...formData, country_season_end_date: e.target.value })} className="h-8 dark:bg-gray-700" />
                                            </div>
                                        </div>
                                    </div>

                                    {/* Regional Season */}
                                    <div className="grid grid-cols-3 gap-2 items-center">
                                        <span className="text-xs font-semibold text-blue-900 dark:text-blue-200">{t('admin.rounds.regional_season') || 'Saison Régionale'}</span>
                                        <div className="col-span-2 grid grid-cols-2 gap-2">
                                            <div>
                                                <label className="block text-[10px] mb-1 opacity-70">{t('admin.rounds.start_date') || 'Début'}</label>
                                                <Input type="date" value={formData.regional_start_date} onChange={(e) => setFormData({ ...formData, regional_start_date: e.target.value })} className="h-8 dark:bg-gray-700" />
                                            </div>
                                            <div>
                                                <label className="block text-[10px] mb-1 opacity-70">{t('admin.rounds.end_date') || 'Fin'}</label>
                                                <Input type="date" value={formData.regional_end_date} onChange={(e) => setFormData({ ...formData, regional_end_date: e.target.value })} className="h-8 dark:bg-gray-700" />
                                            </div>
                                        </div>
                                    </div>

                                    {/* Continental Season */}
                                    <div className="grid grid-cols-3 gap-2 items-center">
                                        <span className="text-xs font-semibold text-blue-900 dark:text-blue-200">{t('admin.rounds.continental_season') || 'Saison Continentale'}</span>
                                        <div className="col-span-2 grid grid-cols-2 gap-2">
                                            <div>
                                                <label className="block text-[10px] mb-1 opacity-70">{t('admin.rounds.start_date') || 'Début'}</label>
                                                <Input type="date" value={formData.continental_start_date} onChange={(e) => setFormData({ ...formData, continental_start_date: e.target.value })} className="h-8 dark:bg-gray-700" />
                                            </div>
                                            <div>
                                                <label className="block text-[10px] mb-1 opacity-70">{t('admin.rounds.end_date') || 'Fin'}</label>
                                                <Input type="date" value={formData.continental_end_date} onChange={(e) => setFormData({ ...formData, continental_end_date: e.target.value })} className="h-8 dark:bg-gray-700" />
                                            </div>
                                        </div>
                                    </div>

                                    {/* Global Season */}
                                    <div className="grid grid-cols-3 gap-2 items-center">
                                        <span className="text-xs font-semibold text-blue-900 dark:text-blue-200">{t('admin.rounds.global_season') || 'Saison Mondiale'}</span>
                                        <div className="col-span-2 grid grid-cols-2 gap-2">
                                            <div>
                                                <label className="block text-[10px] mb-1 opacity-70">{t('admin.rounds.start_date') || 'Début'}</label>
                                                <Input type="date" value={formData.global_start_date} onChange={(e) => setFormData({ ...formData, global_start_date: e.target.value })} className="h-8 dark:bg-gray-700" />
                                            </div>
                                            <div>
                                                <label className="block text-[10px] mb-1 opacity-70">{t('admin.rounds.end_date') || 'Fin'}</label>
                                                <Input type="date" value={formData.global_end_date} onChange={(e) => setFormData({ ...formData, global_end_date: e.target.value })} className="h-8 dark:bg-gray-700" />
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="flex justify-end gap-3 pt-4 border-t dark:border-gray-700">
                            <Button
                                type="button"
                                variant="outline"
                                onClick={onClose}
                                className="dark:bg-gray-700 dark:text-white dark:hover:bg-gray-600"
                            >
                                {t('common.cancel') || 'Annuler'}
                            </Button>
                            <Button
                                type="submit"
                                className="bg-myhigh5-primary hover:bg-myhigh5-primary/90 text-white"
                                disabled={isSubmitting}
                            >
                                {isSubmitting ? (t('common.saving') || 'Enregistrement...') : (t('common.save') || 'Enregistrer')}
                            </Button>
                        </div>
                    </form>
                </CardContent>
            </Card>
        </div>
    )
}
