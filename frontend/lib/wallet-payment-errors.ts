/**
 * Maps wallet / RPC / ethers errors to short, non-technical copy for end users.
 */

const BSC_HINT =
  'Use BNB Smart Chain (BSC) in your wallet, make sure you have enough USDT (BEP-20), then try again. You can switch network in your wallet and refresh this page.'

export function getWalletPaymentUserMessage(err: unknown): string {
  const e = err as {
    message?: string
    reason?: string
    code?: string | number
    shortMessage?: string
  }
  const raw = [e?.shortMessage, e?.message, e?.reason, err instanceof Error ? err.message : null, String(err)]
    .filter(Boolean)
    .join(' ')
  const msg = raw || ''
  const lower = msg.toLowerCase()

  if (lower.includes('insufficient usdt') || (lower.includes('insufficient') && lower.includes('balance'))) {
    return 'Your USDT balance is too low for this payment. Add USDT on BNB Smart Chain (BEP-20), then try again.'
  }

  if (
    lower.includes('user rejected') ||
    lower.includes('user denied') ||
    lower.includes('rejected the request') ||
    e?.code === 'ACTION_REJECTED' ||
    e?.code === 4001
  ) {
    return 'You cancelled the action in your wallet. Nothing was charged.'
  }

  if (
    lower.includes('call_exception') ||
    lower.includes('missing revert data') ||
    lower.includes('could not coalesce error') ||
    (lower.includes('transaction') && lower.includes('reverted'))
  ) {
    return `We could not read your USDT or complete the contract call. ${BSC_HINT}`
  }

  if (lower.includes('network') || lower.includes('chain') || lower.includes('wrong network')) {
    return `Network issue: switch your wallet to BNB Smart Chain (BSC, chain ID 56), then try again. ${BSC_HINT}`
  }

  if (lower.includes('timeout') || lower.includes('timed out') || lower.includes('econnaborted')) {
    return 'The request took too long. Check your internet connection, then try again.'
  }

  if (lower.includes('wallet not connected') || lower.includes('not connected')) {
    return 'Connect your wallet first, then try the payment again.'
  }

  if (lower.includes('failed to add bsc')) {
    return 'Could not add BNB Smart Chain to your wallet. Add the BSC network manually in your wallet settings, then try again.'
  }

  // Long technical ethers / JSON-RPC blobs — never show raw
  if (msg.length > 220 || lower.includes('invocation=null') || lower.includes('version=6.')) {
    return `Something went wrong with the payment. ${BSC_HINT}`
  }

  // Short, already human messages from our code
  if (msg.length > 0 && msg.length < 180 && !lower.includes('0x') && !lower.includes('json-rpc')) {
    return msg
  }

  return `Payment could not be completed. ${BSC_HINT}`
}
