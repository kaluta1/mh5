import AdminBusinessModel from '@/components/admin/admin-business-model'

export const metadata = {
    title: 'Business model | Admin | MyHigh5',
    description: 'Direct affiliate, MyHigh5 Leaders and marketplace administration (Referral Pool history)',
}

export default function BusinessModelAdminPage() {
    return (
        <div className="container mx-auto py-6">
            <AdminBusinessModel />
        </div>
    )
}
