'use client'

import { MarketplaceDashboard } from '@/components/dashboard/marketplace-dashboard'

/** Member marketplace: browse, purchases, sales and the member's own listings (closed while MARKETPLACE_ENABLED is off). */
export default function MarketplacePage() {
  return <MarketplaceDashboard />
}
