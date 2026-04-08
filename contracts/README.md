# MyHigh5PaymentHub (BSC)

Solidity source: `MyHigh5PaymentHub.sol`.

## Role

- Users pay **USDT (BEP-20)** for services (KYC, memberships, etc.) with a **`bytes32 orderId`** issued by the API.
- The contract pulls USDT via **`transferFrom`** from the user **directly to `treasury`** (user must **approve** the hub first). Funds are not held in the hub; there is no owner “withdraw” on the contract.
- It records one payment per `orderId` and emits **`PaymentReceived(orderId, payer, amount, token)`**.
- The backend verifies the tx by reading that event (`app/services/onchain_payment.py`) and then runs **commissions + chart-of-accounts** posting (`payment_accounting.py`).

## Deploy (example: Remix / Foundry / Hardhat)

1. Compile with **Solidity ^0.8.24**.
2. Deploy with constructor arg **`_treasury`**: the wallet that receives **all** incoming native and ERC20 payments (e.g. platform or cold wallet).
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

## Troubleshooting

### Wallet shows `execution reverted` with data `0x6a172882`

That hex is the selector for custom error **`UnsupportedToken()`**: **`payToken` was called with a token that is not allowlisted.**

After **every new hub deployment**, the deployer (owner) **must** call on BSC:

```text
setAcceptedToken(0x55d398326f99059fF775485246999027B3197955, true)
```

Use the same checksummed USDT address as `BSC_USDT_ADDRESS` / `NEXT_PUBLIC_BSC_USDT_ADDRESS`. Without this, `payToken` always reverts at `estimateGas` / execution.

You can run this from **Remix** (connect owner wallet), **Hardhat script**, or **cast send** (Foundry).

### User must approve USDT for the hub

Before `payToken`, the user’s wallet must **approve** the payment contract to spend USDT (the app does this in the payment flow). If approval is missing or too low, you may see a different revert (e.g. transfer failures).

## ABI

The frontend bundles `frontend/lib/payment-hub-abi.json`. After changing the contract interface, regenerate the ABI and replace that file.
