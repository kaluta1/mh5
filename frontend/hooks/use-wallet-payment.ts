/**
 * Hook for wallet connection and smart contract payment execution
 */
import { useState, useCallback } from 'react'
import { BrowserProvider, Contract, parseUnits } from 'ethers'
import { initReownProvider, getReownProvider } from '@/lib/wallet'
import { PAYMENT_CONTRACT_ABI, ERC20_ABI, CONTRACT_ADDRESSES, NETWORK_CONFIG } from '@/lib/contracts'
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

export function useWalletPayment(): UseWalletPaymentReturn {
  const [isConnecting, setIsConnecting] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [connectedAddress, setConnectedAddress] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const connectInjectedWallet = useCallback(async (): Promise<string> => {
    setIsConnecting(true)
    setError(null)

    try {
      if (typeof window === 'undefined' || !window.ethereum) {
        throw new Error('MetaMask or another browser wallet is not installed')
      }

      const provider = new BrowserProvider(window.ethereum)
      const accounts = await provider.send('eth_requestAccounts', [])

      if (accounts.length > 0) {
        const address = accounts[0]
        setConnectedAddress(address)

        const network = await provider.getNetwork()
        if (Number(network.chainId) !== CONTRACTS.CHAIN_ID) {
          await switchToBSCNetwork(provider)
        }

        setIsConnecting(false)
        return address
      }

      throw new Error('No wallet connected')
    } catch (err: any) {
      const errorMessage = err.message || 'Failed to connect browser wallet'
      setError(errorMessage)
      setIsConnecting(false)
      throw new Error(errorMessage)
    }
  }, [])

  const connectWalletConnect = useCallback(async (): Promise<string> => {
    setIsConnecting(true)
    setError(null)

    try {
      const reownProvider = await initReownProvider()
      await reownProvider.enable()

      const accounts = reownProvider.accounts
      if (accounts.length > 0) {
        const address = accounts[0]
        setConnectedAddress(address)
        setIsConnecting(false)
        return address
      }

      throw new Error('No wallet connected')
    } catch (err: any) {
      const errorMessage = err.message || 'Failed to connect wallet'
      setError(errorMessage)
      setIsConnecting(false)
      throw new Error(errorMessage)
    }
  }, [])

  const connectWallet = useCallback(async (): Promise<string> => {
    return connectWalletConnect()
  }, [connectWalletConnect])

  const switchToBSC = useCallback(async (): Promise<void> => {
    if (typeof window === 'undefined' || !window.ethereum) {
      throw new Error('MetaMask not installed')
    }

    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: `0x${CONTRACTS.CHAIN_ID.toString(16)}` }],
      })
    } catch (switchError: any) {
      // This error code indicates that the chain has not been added to MetaMask
      if (switchError.code === 4902) {
        try {
          await window.ethereum.request({
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

  const switchToBSCNetwork = async (provider: BrowserProvider): Promise<void> => {
    if (typeof window === 'undefined' || !window.ethereum) {
      return
    }

    try {
      await window.ethereum.request({
        method: 'wallet_switchEthereumChain',
        params: [{ chainId: `0x${CONTRACTS.CHAIN_ID.toString(16)}` }],
      })
    } catch (switchError: any) {
      if (switchError.code === 4902) {
        await window.ethereum.request({
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
      }
    }
  }

  const executePayment = useCallback(async (
    payment: PaymentResponse,
    token: string
  ): Promise<string> => {
    setIsProcessing(true)
    setError(null)

    try {
      // Get provider and signer
      let provider: BrowserProvider
      const reownProvider = getReownProvider()
      if (reownProvider) {
        provider = new BrowserProvider(reownProvider)
      } else if (typeof window !== 'undefined' && window.ethereum) {
        provider = new BrowserProvider(window.ethereum)
      } else {
        throw new Error('Wallet not connected')
      }

      const signer = await provider.getSigner()
      const payerAddress = await signer.getAddress()

      // Ensure we're on BSC
      const network = await provider.getNetwork()
      if (Number(network.chainId) !== CONTRACTS.CHAIN_ID) {
        await switchToBSCNetwork(provider)
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
  }, [])

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
