/**
 * Smart Contract ABIs and Addresses
 */
import paymentHubAbi from './payment-hub-abi.json'

/** MyHigh5PaymentHub — matches deployed contract + backend on-chain verifier */
export const PAYMENT_CONTRACT_ABI = paymentHubAbi

// ERC20 Token ABI (Ethers.js format)
export const ERC20_ABI = [
  'function approve(address spender, uint256 amount) returns (bool)',
  'function allowance(address owner, address spender) view returns (uint256)',
  'function balanceOf(address owner) view returns (uint256)',
  'function transfer(address to, uint256 amount) returns (bool)'
] as const

// Contract Addresses
export const CONTRACT_ADDRESSES = {
  PAYMENT_CONTRACT: '0xC003750eDf5feEFBf94FB4B754D70f2b73392Ea9',
  USDT: '0x55d398326f99059fF775485246999027B3197955'
} as const

// Network Configuration
export const NETWORK_CONFIG = {
  CHAIN_ID: 56,
  RPC_URL: 'https://bsc-dataseed.binance.org',
  EXPLORER_URL: 'https://bscscan.com',
  USDT_DECIMALS: 18
} as const
