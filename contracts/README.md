# MyHigh5PaymentHub (BSC)

Solidity source: `MyHigh5PaymentHub.sol`.

## Role

- Users pay **USDT (BEP-20)** for services (KYC, memberships, etc.) with a **`bytes32 orderId`** issued by the API.
- The contract pulls USDT via **`transferFrom`** (user must **approve** the hub first), records one payment per `orderId`, and emits **`PaymentReceived(orderId, payer, amount, token)`**.
- The backend verifies the tx by reading that event (`app/services/onchain_payment.py`) and then runs **commissions + chart-of-accounts** posting (`payment_accounting.py`).

## Deploy (example: Remix / Foundry / Hardhat)

1. Compile with **Solidity ^0.8.24**.
2. Deploy with constructor arg **`_treasury`**: your platform wallet that receives withdrawals (or a cold wallet).
3. After deploy, **owner** must call:
   - **`setAcceptedToken(<BSC_USDT>, true)`** — mainnet USDT on BSC: `0x55d398326f99059fF775485246999027B3197955` (confirm on [BscScan](https://bscscan.com)).
4. Copy the deployed **hub address** into env (see below).

## Env alignment (critical)

The **same** hub + USDT addresses must be set for:

| Layer | Variable |
|--------|-----------|
| Backend | `BSC_PAYMENT_CONTRACT`, `BSC_USDT_ADDRESS`, `BSC_RPC_URL`, `BSC_CHAIN_ID` |
| Frontend (Vercel / build) | `NEXT_PUBLIC_BSC_PAYMENT_CONTRACT`, `NEXT_PUBLIC_BSC_USDT_ADDRESS`, optional `NEXT_PUBLIC_BSC_CHAIN_ID`, etc. |

If any of these disagree, payments or verification will fail.

## ABI

The frontend bundles `frontend/lib/payment-hub-abi.json`. After changing the contract interface, regenerate the ABI and replace that file.
