import AdminReferralPool from '@/components/admin/admin-referral-pool'

export const metadata = {
    title: 'Referral Pool | Admin | MyHigh5',
    description: 'Multi-Unit Referral Pool administration: units, rounds, allocation, purchases, refunds and reviews',
}

export default function ReferralPoolAdminPage() {
    return (
        <div className="container mx-auto py-6">
            <AdminReferralPool />
        </div>
    )
}
