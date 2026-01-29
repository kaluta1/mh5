import AdminAccounting from '@/components/admin/admin-accounting'

export const metadata = {
    title: 'Comptabilité | Admin | MyHigh5',
    description: 'Gestion comptable et financière',
}

export default function AccountingPage() {
    return (
        <div className="container mx-auto py-6">
            <AdminAccounting />
        </div>
    )
}
