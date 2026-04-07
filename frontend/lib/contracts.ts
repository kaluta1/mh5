/**
 * Smart Contract ABIs and Addresses (single source: lib/config.ts CONTRACTS)
 */
import paymentHubAbi from './payment-hub-abi.json'
import { CONTRACTS } from './config'

/** MyHigh5PaymentHub — matches contracts/MyHigh5PaymentHub.sol + backend verifier */
export const PAYMENT_CONTRACT_ABI = paymentHubAbi

// ERC20 Token ABI (Ethers.js format)
export const ERC20_ABI = [
  'function approve(address spender, uint256 amount) returns (bool)',
  'function allowance(address owner, address spender) view returns (uint256)',
  'function balanceOf(address owner) view returns (uint256)',
  'function transfer(address to, uint256 amount) returns (bool)'
] as const

export const CONTRACT_ADDRESSES = {
  PAYMENT_CONTRACT: CONTRACTS.PAYMENT_CONTRACT,
  USDT: CONTRACTS.USDT_ADDRESS
} as const

export const NETWORK_CONFIG = {
  CHAIN_ID: CONTRACTS.CHAIN_ID,
  RPC_URL: CONTRACTS.RPC_URL,
  EXPLORER_URL: CONTRACTS.EXPLORER_URL,
  USDT_DECIMALS: CONTRACTS.USDT_DECIMALS
} as const
