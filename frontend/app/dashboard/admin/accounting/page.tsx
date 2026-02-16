import AdminAccounting from '@/components/admin/admin-accounting'

export const metadata = {
    title: 'Accounting | Admin | MyHigh5',
    description: 'Accounting and financial management',
}

export default function AccountingPage() {
    return (
        <div className="container mx-auto py-6">
            <AdminAccounting />
        </div>
    )
}
