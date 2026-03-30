/**
 * Reown/WalletConnect Provider Setup
 */
import { EthereumProvider } from '@walletconnect/ethereum-provider'
import { REOWN_PROJECT_ID } from './config'

let walletConnectProvider: InstanceType<typeof EthereumProvider> | null = null

export const initReownProvider = async (): Promise<InstanceType<typeof EthereumProvider>> => {
  if (!REOWN_PROJECT_ID) {
    throw new Error('Reown wallet connect is not configured. Set NEXT_PUBLIC_REOWN_PROJECT_ID in your frontend environment before deploying.')
  }

  if (walletConnectProvider) {
    return walletConnectProvider
  }

  walletConnectProvider = await EthereumProvider.init({
    projectId: REOWN_PROJECT_ID,
    chains: [56], // BSC Mainnet
    showQrModal: true,
    qrModalOptions: {
      enableExplorer: true,
      themeMode: 'light',
    },
    rpcMap: {
      56: 'https://bsc-dataseed.binance.org'
    },
    metadata: {
      name: 'MyHigh5',
      description: 'MyHigh5 payments',
      url: typeof window !== 'undefined' ? window.location.origin : 'https://myhigh5.com',
      icons: ['https://myhigh5.com/favicon.ico']
    }
  })

  return walletConnectProvider
}

export const getReownProvider = (): InstanceType<typeof EthereumProvider> | null => {
  return walletConnectProvider
}
