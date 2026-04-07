# Smart contract payments → services → chart of accounts

This stack already wires **on-chain USDT (BSC)** to **deposits**, **affiliate commissions**, and **double-entry journals** (plan comptable).

## End-to-end flow

1. **Create order (API)**  
   `POST /api/v1/payments/create` with `product_code` (e.g. `kyc`, membership codes from `product_types`).  
   Returns `order_id` (bytes32 hex), `amount_wei`, `contract_address`, `token_address`.

2. **Wallet (website)**  
   User connects wallet (Reown / MetaMask), switches to **BSC**, **approves** USDT to **MyHigh5PaymentHub**, calls **`payToken(orderId, USDT, amount)`**.  
   Implementation: `frontend/hooks/use-wallet-payment.ts`, addresses from `frontend/lib/config.ts` / `lib/contracts.ts`.

3. **Verify (API)**  
   `POST /api/v1/payments/verify` with `order_id` + `tx_hash`.  
   `app/services/onchain_payment.py` reads the receipt, finds **`PaymentReceived`** for that `order_id`, checks amount/token.

4. **Business logic**  
   `process_payment_validation` → commissions (`commission_distribution.py`) and, for validated flows, **accounting** via `payment_accounting.py` + `accounting_service.create_journal_entry` using **account codes** (e.g. `1001` Platform wallet, `4001` KYC revenue, `5001` commission expense, `2001`/`2002` payables) aligned with `init_coa.py` / CoA docs.

5. **Admin**  
   Chart of accounts + journal views read the **database** (`/api/v1/admin/accounting/...`), not the chain directly. The chain is the **source of truth for settlement**; the DB is the **source of truth for recognition** after verification.

## Contract source

- `contracts/MyHigh5PaymentHub.sol`

## Configuration

- Backend: `app/core/config.py` (`BSC_*`).
- Frontend: `NEXT_PUBLIC_BSC_*` in `frontend/lib/config.ts`.

## Adding a new paid service

1. Add / reuse a **`product_types`** row and `product_code`.
2. Ensure **create payment** + **verify** paths work for that product.
3. Extend **`payment_accounting.py`** (and commission rules if needed) so the right **journal lines** hit the right **CoA codes**.
4. Optionally document new lines in `docs/MYHIGH5_CHART_OF_ACCOUNTS.md`.
