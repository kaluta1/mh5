/**
 * Type declarations for window.ethereum (MetaMask and other wallet providers)
 */
interface Window {
  ethereum?: {
    request: (args: { method: string; params?: any[] }) => Promise<any>
    isMetaMask?: boolean
    isConnected?: () => boolean
    on?: (event: string, handler: (...args: any[]) => void) => void
    removeListener?: (event: string, handler: (...args: any[]) => void) => void
  }
}
