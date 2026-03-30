'use client'

import type { ReactNode } from 'react'
import { AppKitProvider } from '@reown/appkit/react'
import { EthersAdapter } from '@reown/appkit-adapter-ethers'
import { defineChain } from '@reown/appkit/networks'
import { REOWN_PROJECT_ID, CONTRACTS } from '@/lib/config'

const bscNetwork = defineChain({
  id: CONTRACTS.CHAIN_ID,
  caipNetworkId: `eip155:${CONTRACTS.CHAIN_ID}`,
  chainNamespace: 'eip155',
  name: 'BNB Smart Chain',
  nativeCurrency: {
    name: 'BNB',
    symbol: 'BNB',
    decimals: 18,
  },
  rpcUrls: {
    default: {
      http: [CONTRACTS.RPC_URL],
    },
  },
  blockExplorers: {
    default: {
      name: 'BscScan',
      url: CONTRACTS.EXPLORER_URL,
    },
  },
})

const metadata = {
  name: 'MyHigh5',
  description: 'MyHigh5 wallet connection',
  url: process.env.NEXT_PUBLIC_APP_URL || 'https://myhigh5.com',
  icons: ['https://myhigh5.com/favicon.ico'],
}

const ethersAdapter = new EthersAdapter()

export function ReownAppKitProvider({ children }: { children: ReactNode }) {
  if (!REOWN_PROJECT_ID) {
    return <>{children}</>
  }

  return (
    <AppKitProvider
      adapters={[ethersAdapter]}
      projectId={REOWN_PROJECT_ID}
      networks={[bscNetwork]}
      defaultNetwork={bscNetwork}
      metadata={metadata}
      defaultAccountTypes={{ eip155: 'eoa' }}
      features={{ analytics: false }}
    >
      {children}
    </AppKitProvider>
  )
}
