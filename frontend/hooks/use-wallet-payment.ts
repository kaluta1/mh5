/**
 * Hook for wallet connection and smart contract payment execution
 */
import { useState, useCallback, useEffect, useRef } from 'react'
import { BrowserProvider, Contract } from 'ethers'
import { useAppKit, useAppKitAccount, useAppKitProvider } from '@reown/appkit/react'
import type { ProviderType } from '@reown/appkit-adapter-ethers'
import { PAYMENT_CONTRACT_ABI, ERC20_ABI, CONTRACT_ADDRESSES } from '@/lib/contracts'
import { CONTRACTS } from '@/lib/config'
import { paymentService, PaymentResponse } from '@/services/payment-service'

interface UseWalletPaymentReturn {
  isConnecting: boolean
  isProcessing: boolean
  connectedAddress: string | null
  error: string | null
  connectWallet: () => Promise<string>
  connectInjectedWallet: () => Promise<string>
  connectWalletConnect: () => Promise<string>
  executePayment: (payment: PaymentResponse, token: string) => Promise<string>
  switchToBSC: () => Promise<void>
}

type Eip1193RequestProvider = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>
}

export function useWalletPayment(): UseWalletPaymentReturn {
  const { open } = useAppKit()
  const { address, isConnected } = useAppKitAccount()
  const { walletProvider } = useAppKitProvider<ProviderType>('eip155')
  const [isConnecting, setIsConnecting] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [connectedAddress, setConnectedAddress] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const connectedAddressRef = useRef<string | null>(null)
  const walletProviderRef = useRef<ProviderType | undefined>(walletProvider)

  useEffect(() => {
    const nextAddress = isConnected && address ? address : null
    connectedAddressRef.current = nextAddress
    walletProviderRef.current = walletProvider
    setConnectedAddress(nextAddress)

    if (nextAddress) {
      setError(null)
    }
  }, [address, isConnected, walletProvider])

  const waitForWalletConnection = useCallback(async (): Promise<string> => {
    const timeoutMs = 60000
    const pollMs = 300
    const startedAt = Date.now()

    while (Date.now() - startedAt < timeoutMs) {
      if (connectedAddressRef.current && walletProviderRef.current) {
        return connectedAddressRef.current
      }

      await new Promise(resolve => setTimeout(resolve, pollMs))
    }

    throw new Error('Wallet connection was not completed. Please choose a wallet in Reown and approve the connection.')
  }, [])

  const switchToBSC = useCallback(async (): Promise<void> => {
    const provider = walletProviderRef.current as unknown as Eip1193RequestProvider | undefined
    if (!provider) {
      throw new Error('Wallet not connected')
    }

    try {
      await provider.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: `0x${CONTRACTS.CHAIN_ID.toString(16)}` }],
      })
    } catch (switchError: any) {
      // This error code indicates that the chain has not been added to MetaMask
      if (switchError.code === 4902) {
        try {
          await provider.request({
            method: 'wallet_addEthereumChain',
            params: [
              {
                chainId: `0x${CONTRACTS.CHAIN_ID.toString(16)}`,
                chainName: 'BNB Smart Chain',
                nativeCurrency: {
                  name: 'BNB',
                  symbol: 'BNB',
                  decimals: 18,
                },
                rpcUrls: [CONTRACTS.RPC_URL],
                blockExplorerUrls: [CONTRACTS.EXPLORER_URL],
              },
            ],
          })
        } catch (addError) {
          throw new Error('Failed to add BSC network to MetaMask')
        }
      } else {
        throw switchError
      }
    }
  }, [])

  const connectWalletConnect = useCallback(async (): Promise<string> => {
    setIsConnecting(true)
    setError(null)

    try {
      if (connectedAddressRef.current && walletProviderRef.current) {
        setIsConnecting(false)
        return connectedAddressRef.current
      }

      await open({ view: 'Connect' })
      const connected = await waitForWalletConnection()
      await switchToBSC()
      setIsConnecting(false)
      return connected
    } catch (err: any) {
      const rawMessage = String(err?.message || '')
      const errorMessage =
        rawMessage.includes('Connection request reset')
          ? 'Wallet connection expired or was cancelled. Please open the Reown wallet list and try again.'
          : rawMessage || 'Failed to connect wallet'
      setError(errorMessage)
      setIsConnecting(false)
      throw new Error(errorMessage)
    }
  }, [open, switchToBSC, waitForWalletConnection])

  const connectInjectedWallet = useCallback(async (): Promise<string> => {
    return connectWalletConnect()
  }, [connectWalletConnect])

  const connectWallet = useCallback(async (): Promise<string> => {
    return connectWalletConnect()
  }, [connectWalletConnect])

  const switchToBSCNetwork = async (): Promise<void> => {
    await switchToBSC()
  }

  const executePayment = useCallback(async (
    payment: PaymentResponse,
    token: string
  ): Promise<string> => {
    setIsProcessing(true)
    setError(null)

    try {
      // Get provider and signer
      const walletProvider = walletProviderRef.current
      if (!walletProvider) {
        throw new Error('Wallet not connected')
      }

      const provider = new BrowserProvider(walletProvider as unknown as Eip1193RequestProvider)

      const signer = await provider.getSigner()
      const payerAddress = await signer.getAddress()

      // Ensure we're on BSC
      const network = await provider.getNetwork()
      if (Number(network.chainId) !== CONTRACTS.CHAIN_ID) {
        await switchToBSCNetwork()
        // Wait a bit for network switch
        await new Promise(resolve => setTimeout(resolve, 1000))
      }

      // Get token contract
      const tokenContract = new Contract(
        CONTRACT_ADDRESSES.USDT,
        ERC20_ABI,
        signer
      )

      // Check balance
      const balance = await tokenContract.balanceOf(payerAddress)
      const requiredAmount = BigInt(payment.amount_wei)
      
      if (balance < requiredAmount) {
        throw new Error('Insufficient USDT balance')
      }

      // Check and approve if needed
      const allowance = await tokenContract.allowance(
        payerAddress,
        CONTRACT_ADDRESSES.PAYMENT_CONTRACT
      )

      if (allowance < requiredAmount) {
        // Approve transaction
        const approveTx = await tokenContract.approve(
          CONTRACT_ADDRESSES.PAYMENT_CONTRACT,
          requiredAmount
        )
        await approveTx.wait()
      }

      // Execute payment
      const paymentContract = new Contract(
        CONTRACT_ADDRESSES.PAYMENT_CONTRACT,
        PAYMENT_CONTRACT_ABI,
        signer
      )

      const tx = await paymentContract.payToken(
        payment.order_id,
        CONTRACT_ADDRESSES.USDT,
        requiredAmount
      )

      const receipt = await tx.wait()

      if (!receipt || !receipt.hash) {
        throw new Error('Transaction failed')
      }

      // Verify payment with backend
      await paymentService.verifyPayment(token, {
        order_id: payment.order_id,
        tx_hash: receipt.hash
      })

      setIsProcessing(false)
      return receipt.hash
    } catch (err: any) {
      const errorMessage = err.message || 'Payment failed'
      setError(errorMessage)
      setIsProcessing(false)
      throw new Error(errorMessage)
    }
  }, [switchToBSC])

  return {
    isConnecting,
    isProcessing,
    connectedAddress,
    error,
    connectWallet,
    connectInjectedWallet,
    connectWalletConnect,
    executePayment,
    switchToBSC
  }
}
