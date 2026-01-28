'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Plus, Edit2, Trash2, Search, Filter, Trophy, Calendar, Users, CheckCircle2, AlertCircle } from 'lucide-react'
import { ContestDialog } from './ContestDialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { contestService, type ContestResponse } from '@/lib/services/contest-service'
import api from '@/lib/api'

interface ContestListProps {
    seasons: any[]
    votingTypes: any[]
    categories: any[]
}

export function ContestList({ seasons, votingTypes, categories }: ContestListProps) {
    const { t } = useLanguage()
    const { addToast } = useToast()
    const router = useRouter()
    const [contests, setContests] = useState<any[]>([])
    const [filteredContests, setFilteredContests] = useState<any[]>([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')
    const [showDialog, setShowDialog] = useState(false)
    const [editingContest, setEditingContest] = useState<any | null>(null)
    const [showDeleteDialog, setShowDeleteDialog] = useState(false)
    const [deleteContestId, setDeleteContestId] = useState<number | null>(null)

    useEffect(() => {
        fetchContests()
    }, [])

    useEffect(() => {
        let filtered = contests.filter(contest =>
            contest.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            contest.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
            contest.contest_type.toLowerCase().includes(searchQuery.toLowerCase())
        )
        setFilteredContests(filtered)
    }, [contests, searchQuery])

    const fetchContests = async () => {
        try {
            setLoading(true)
            const data = await contestService.getAllContests()
            setContests(data)
        } catch (error) {
            console.error('Error fetching contests:', error)
            addToast(t('admin.contests.load_error') || 'Erreur lors du chargement des concours', 'error')
        } finally {
            setLoading(false)
        }
    }

    const handleCreate = (type: 'participation' | 'nomination') => {
        setEditingContest(null)
        // Pre-fill season based on type
        // Participation -> City (level: 'city')
        // Nomination -> Country (level: 'country')
        let initialSeasonId = null
        if (seasons.length > 0) {
            if (type === 'participation') {
                const citySeason = seasons.find(s => s.level?.toLowerCase() === 'city')
                if (citySeason) initialSeasonId = citySeason.id
            } else if (type === 'nomination') {
                const countrySeason = seasons.find(s => s.level?.toLowerCase() === 'country')
                if (countrySeason) initialSeasonId = countrySeason.id
            }
        }

        const initialVotingTypeId = type === 'nomination' && votingTypes.length > 0 ? votingTypes[0].id : null

        // Pass this pre-filled state to the dialog via a new way or just rely on the dialog knowing it's a new contest
        // actually, we can pass a partial object as initialData even for new contests if we want specific fields pre-filled
        setEditingContest({
            isNew: true, // Marker to tell dialog this is a new contest creation
            voting_type_id: initialVotingTypeId,
            season_id: initialSeasonId,
            type: type // 'participation' or 'nomination'
        })
        setShowDialog(true)
    }

    const handleEdit = (contest: any) => {
        setEditingContest(contest)
        setShowDialog(true)
    }

    const handleDelete = (id: number) => {
        setDeleteContestId(id)
        setShowDeleteDialog(true)
    }

    const handleConfirmDelete = async () => {
        if (!deleteContestId) return
        try {
            await contestService.deleteContest(deleteContestId)
            addToast(t('admin.contests.delete_success') || 'Concours supprimé avec succès', 'success')
            fetchContests()
        } catch (error) {
            addToast(t('admin.contests.delete_error') || 'Erreur lors de la suppression', 'error')
        } finally {
            setShowDeleteDialog(false)
            setDeleteContestId(null)
        }
    }

    const handleSave = async (data: any) => {
        // Prepare data for API
        // Similar mapping as was in admin-contests.tsx
        const dataToSend = {
            ...data,
            season_id: data.season_id ? parseInt(data.season_id) : null,
            category_id: data.category_id ? parseInt(data.category_id) : null,
            voting_type_id: data.voting_type_id ? parseInt(data.voting_type_id) : null
        }

        if (editingContest) {
            await contestService.updateContest(editingContest.id, dataToSend)
            addToast(t('admin.contests.update_success') || 'Concours mis à jour avec succès', 'success')
        } else {
            await contestService.createContest(dataToSend)
            addToast(t('admin.contests.create_success') || 'Concours créé avec succès', 'success')
        }
        fetchContests()
    }

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center bg-white dark:bg-gray-800 p-4 rounded-lg shadow-sm border dark:border-gray-700">
                <div className="relative w-72">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <Input
                        placeholder={t('admin.contests.search') || 'Rechercher un concours...'}
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="pl-9 bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700"
                    />
                </div>
                <div className="flex gap-2">
                    <Button onClick={() => handleCreate('participation')} className="bg-blue-600 text-white hover:bg-blue-700">
                        <Plus className="h-4 w-4 mr-2" />
                        {t('admin.contests.new_participation') || 'Nouveau (Participation)'}
                    </Button>
                    <Button onClick={() => handleCreate('nomination')} className="bg-myhigh5-primary text-white hover:bg-myhigh5-primary/90">
                        <Plus className="h-4 w-4 mr-2" />
                        {t('admin.contests.new_nomination') || 'Nouveau (Nomination)'}
                    </Button>
                </div>
            </div>

            {loading ? (
                <div className="flex justify-center p-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-myhigh5-primary"></div>
                </div>
            ) : (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {filteredContests.map((contest) => (
                        <Card key={contest.id} className="group hover:border-myhigh5-primary/50 transition-colors dark:bg-gray-800 dark:border-gray-700">
                            <CardHeader className="flex flex-row items-start justify-between pb-2">
                                <div>
                                    <div className="flex items-center gap-2 mb-1">
                                        {contest.is_active ? (
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
                                                Actif
                                            </span>
                                        ) : (
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300">
                                                Inactif
                                            </span>
                                        )}
                                        <span className="text-xs text-gray-500 dark:text-gray-400 capitalize bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
                                            {contest.level}
                                        </span>
                                    </div>
                                    <CardTitle className="text-lg font-bold line-clamp-1 group-hover:text-myhigh5-primary transition-colors">
                                        {contest.name}
                                    </CardTitle>
                                </div>
                            </CardHeader>
                            <CardContent>
                                {contest.image_url && (
                                    <div className="mb-4 h-32 w-full overflow-hidden rounded-md">
                                        <img
                                            src={contest.image_url}
                                            alt={contest.name}
                                            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                                        />
                                    </div>
                                )}
                                <div className="space-y-2 text-sm text-gray-600 dark:text-gray-300">
                                    <div className="flex items-center gap-2">
                                        <Calendar className="h-4 w-4 text-gray-400" />
                                        <span>Du {new Date(contest.submission_start_date).toLocaleDateString()} au {new Date(contest.submission_end_date).toLocaleDateString()}</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <Users className="h-4 w-4 text-gray-400" />
                                        <span>{contest.participant_count || 0} participants</span>
                                    </div>
                                </div>

                                <div className="flex justify-end gap-2 mt-4 pt-4 border-t dark:border-gray-700">
                                    <Button variant="ghost" size="sm" onClick={() => handleEdit(contest)}>
                                        <Edit2 className="h-4 w-4" />
                                    </Button>
                                    <Button variant="ghost" size="sm" className="text-red-500 hover:text-red-600" onClick={() => handleDelete(contest.id)}>
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}

            <ContestDialog
                isOpen={showDialog}
                onClose={() => setShowDialog(false)}
                onSave={handleSave}
                initialData={editingContest}
                seasons={seasons}
                votingTypes={votingTypes}
                categories={categories}
                isVotingTypeDisabled={false}
            />

            <ConfirmDialog
                open={showDeleteDialog}
                onOpenChange={setShowDeleteDialog}
                onConfirm={handleConfirmDelete}
                title={t('admin.contests.confirm_delete') || 'Confirmer la suppression'}
                message={t('admin.contests.delete_warning') || 'Cette action est irréversible. Voulez-vous vraiment supprimer ce concours ?'}
            />
        </div>
    )
}
