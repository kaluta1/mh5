'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/contexts/language-context'
import { useToast } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Plus, Edit2, Trash2, Search, Calendar, CheckCircle2, AlertCircle } from 'lucide-react'
import { RoundDialog } from './RoundDialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import api from '@/lib/api'
import { contestService } from '@/lib/services/contest-service'

export function RoundsList() {
    const { t } = useLanguage()
    const { addToast } = useToast()
    const [rounds, setRounds] = useState<any[]>([])
    const [contests, setContests] = useState<any[]>([]) // For the dialog select
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')
    const [showDialog, setShowDialog] = useState(false)
    const [editingRound, setEditingRound] = useState<any | null>(null)
    const [showDeleteDialog, setShowDeleteDialog] = useState(false)
    const [deleteRoundId, setDeleteRoundId] = useState<number | null>(null)

    useEffect(() => {
        fetchRounds()
        fetchContests()
    }, [])

    const fetchRounds = async () => {
        try {
            setLoading(true)
            const response = await api.get('/api/v1/rounds/')
            setRounds(response.data)
        } catch (error) {
            console.error('Error fetching rounds:', error)
            addToast(t('admin.rounds.load_error') || 'Erreur lors du chargement des rounds', 'error')
        } finally {
            setLoading(false)
        }
    }

    const fetchContests = async () => {
        try {
            const data = await contestService.getAllContests()
            setContests(data)
        } catch (error) {
            console.error('Error fetching contests for rounds:', error)
        }
    }

    const handleCreate = () => {
        setEditingRound(null)
        setShowDialog(true)
    }

    const handleEdit = (round: any) => {
        setEditingRound(round)
        setShowDialog(true)
    }

    const handleDelete = (id: number) => {
        setDeleteRoundId(id)
        setShowDeleteDialog(true)
    }

    const handleConfirmDelete = async () => {
        if (!deleteRoundId) return
        try {
            await api.delete(`/api/v1/rounds/${deleteRoundId}`)
            addToast(t('admin.rounds.delete_success') || 'Round supprimé avec succès', 'success')
            fetchRounds()
        } catch (error) {
            addToast(t('admin.rounds.delete_error') || 'Erreur lors de la suppression', 'error')
        } finally {
            setShowDeleteDialog(false)
            setDeleteRoundId(null)
        }
    }

    const handleSave = async (data: any) => {
        const dataToSend = {
            ...data,
            contest_id: parseInt(data.contest_id)
        }

        if (editingRound) {
            await api.put(`/api/v1/rounds/${editingRound.id}`, dataToSend)
            addToast(t('admin.rounds.update_success') || 'Round mis à jour avec succès', 'success')
        } else {
            await api.post('/api/v1/rounds/', dataToSend)
            addToast(t('admin.rounds.create_success') || 'Round créé avec succès', 'success')
        }
        fetchRounds()
    }

    const filteredRounds = rounds.filter(round =>
        round.name.toLowerCase().includes(searchQuery.toLowerCase())
    )

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center bg-white dark:bg-gray-800 p-4 rounded-lg shadow-sm border dark:border-gray-700">
                <div className="relative w-72">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <Input
                        placeholder={t('admin.rounds.search') || 'Rechercher un round...'}
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="pl-9 bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700"
                    />
                </div>
                <Button onClick={handleCreate} className="bg-myhigh5-primary text-white hover:bg-myhigh5-primary/90">
                    <Plus className="h-4 w-4 mr-2" />
                    {t('admin.rounds.new_round') || 'Nouveau Round'}
                </Button>
            </div>

            {loading ? (
                <div className="flex justify-center p-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-myhigh5-primary"></div>
                </div>
            ) : (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {filteredRounds.map((round) => (
                        <Card key={round.id} className="group hover:border-myhigh5-primary/50 transition-colors dark:bg-gray-800 dark:border-gray-700">
                            <CardHeader className="flex flex-row items-start justify-between pb-2">
                                <div>
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${round.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'} dark:bg-gray-700 dark:text-gray-300`}>
                                            {round.status}
                                        </span>
                                        {/* Try to find contest name from local list if possible, or api usually returns it? Assuming minimal display for now */}
                                        <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
                                            ID: {round.id}
                                        </span>
                                    </div>
                                    <CardTitle className="text-lg font-bold line-clamp-1 group-hover:text-myhigh5-primary transition-colors">
                                        {round.name}
                                    </CardTitle>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2 text-sm text-gray-600 dark:text-gray-300 mt-2">
                                    <div className="flex items-center gap-2">
                                        <Calendar className="h-4 w-4 text-gray-400" />
                                        <span>Vote: {new Date(round.voting_start_date).toLocaleDateString()} - {new Date(round.voting_end_date).toLocaleDateString()}</span>
                                    </div>
                                </div>

                                <div className="flex justify-end gap-2 mt-4 pt-4 border-t dark:border-gray-700">
                                    <Button variant="ghost" size="sm" onClick={() => handleEdit(round)}>
                                        <Edit2 className="h-4 w-4" />
                                    </Button>
                                    <Button variant="ghost" size="sm" className="text-red-500 hover:text-red-600" onClick={() => handleDelete(round.id)}>
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}

            <RoundDialog
                isOpen={showDialog}
                onClose={() => setShowDialog(false)}
                onSave={handleSave}
                initialData={editingRound}
                contests={contests}
            />

            <ConfirmDialog
                open={showDeleteDialog}
                onOpenChange={(open) => setShowDeleteDialog(open)}
                onConfirm={handleConfirmDelete}
                title={t('admin.rounds.confirm_delete') || 'Confirmer la suppression'}
                message={t('admin.rounds.delete_warning') || 'Voulez-vous vraiment supprimer ce round ?'}
            />
        </div>
    )
}
