# Complete Payment & Accounting Flow

## 📋 Overview

This document explains the complete flow of how payments work from initiation to accounting entries, including commission distribution and accounting integration.

---

## 🔄 Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    PAYMENT FLOW - STEP BY STEP                  │
└─────────────────────────────────────────────────────────────────┘

1. USER INITIATES PAYMENT (Frontend)
   │
   ├─> User selects product (KYC, Membership, etc.)
   ├─> User enters amount
   ├─> User selects payment method (USDT BSC)
   │
   ▼
   
2. CREATE PAYMENT ORDER (Backend API)
   │
   ├─> POST /api/v1/payments/create
   ├─> Generate unique order_id (bytes32 format)
   ├─> Convert amount to wei (for blockchain)
   ├─> Create Deposit record:
   │   ├─ status: PENDING
   │   ├─ order_id: "0x..."
   │   ├─ amount: $100.00
   │   └─ crypto_amount: "100000000000000000000" (wei)
   │
   └─> Return payment details to frontend
       ├─ deposit_id
       ├─ order_id
       ├─ contract_address
       ├─ token_address
       └─ amount_wei
   │
   ▼
   
3. USER EXECUTES PAYMENT (Frontend + Blockchain)
   │
   ├─> Frontend connects wallet (MetaMask/Reown)
   ├─> Check USDT balance
   ├─> Approve USDT if needed
   ├─> Execute smart contract payment
   │   └─> payToken(order_id, amount_wei)
   ├─> Get transaction hash (tx_hash)
   │
   └─> Submit tx_hash to backend
   │
   ▼
   
4. VERIFY PAYMENT (Backend API)
   │
   ├─> POST /api/v1/payments/verify
   ├─> Find deposit by order_id
   ├─> Verify ownership (user must own deposit)
   │
   ├─> BLOCKCHAIN VERIFICATION
   │   ├─> onchain_payment_service.verify_payment()
   │   ├─> Get transaction receipt from BSC
   │   ├─> Verify transaction status = confirmed
   │   ├─> Verify order_id matches
   │   ├─> Verify amount >= expected
   │   └─> Extract payer address
   │
   ├─> Update Deposit:
   │   ├─ status: VALIDATED ✅
   │   ├─ validated_at: timestamp
   │   ├─ external_payment_id: tx_hash
   │   └─ payment_address: payer address
   │
   └─> Call process_payment_validation()
   │
   ▼
   
5. PROCESS PAYMENT VALIDATION (Backend Service)
   │
   ├─> process_payment_validation(deposit)
   │   │
   ├─> STEP 5.1: DISTRIBUTE COMMISSIONS
   │   │
   │   ├─> distribute_commissions(deposit, product_code)
   │   │   │
   │   ├─> Get source user (who paid)
   │   ├─> Check if user has sponsor
   │   │
   │   ├─> Traverse sponsor tree (up to 10 levels):
   │   │   │
   │   │   Level 1 (Direct Sponsor):
   │   │   ├─> KYC ($10): $2 commission
   │   │   ├─> MFM ($100): $20 commission
   │   │   └─> Annual ($50): $10 commission
   │   │   │
   │   │   Levels 2-10 (Indirect Sponsors):
   │   │   ├─> KYC: $0.20 per level
   │   │   ├─> MFM: $2 per level
   │   │   └─> Annual: $1 per level
   │   │
   │   └─> Create AffiliateCommission records:
   │       ├─ user_id: sponsor who gets commission
   │       ├─ source_user_id: user who paid
   │       ├─ commission_amount: calculated amount
   │       ├─ level: 1-10
   │       ├─ status: APPROVED
   │       └─ deposit_id: link to deposit
   │
   │   └─> Commit commissions to database
   │
   ├─> STEP 5.2: CREATE ACCOUNTING ENTRIES ⭐ NEW
   │   │
   │   ├─> record_payment_in_accounting(deposit, commissions)
   │   │   │
   │   ├─> Calculate amounts:
   │   │   ├─ total_amount = deposit.amount ($100)
   │   │   ├─ total_commissions = sum of all commissions ($22)
   │   │   └─ net_revenue = total - commissions ($78)
   │   │
   │   ├─> Get/Create Chart of Accounts:
   │   │   ├─ 1010: Crypto Asset - USDT (Asset)
   │   │   ├─ 4000: Membership Revenue (Revenue) OR
   │   │   ├─ 4010: KYC Service Revenue (Revenue)
   │   │   ├─ 5000: Commission Expense (Expense)
   │   │   └─ 2000: Commission Payable (Liability)
   │   │
   │   ├─> Create Journal Entry:
   │   │   ├─ entry_number: "JE-20260128-ABC12345"
   │   │   ├─ entry_date: deposit.validated_at
   │   │   ├─ description: "Payment received - mfm_membership - Deposit #123"
   │   │   ├─ total_debit: $100.00
   │   │   ├─ total_credit: $100.00
   │   │   └─ status: POSTED ✅
   │   │
   │   ├─> Create Journal Lines (Double-Entry):
   │   │   │
   │   │   Line 1: Debit Crypto Asset
   │   │   ├─ account: 1010 (Crypto Asset)
   │   │   ├─ debit_amount: $100.00
   │   │   └─ credit_amount: $0.00
   │   │
   │   │   Line 2: Credit Revenue (Gross)
   │   │   ├─ account: 4000 (Membership Revenue)
   │   │   ├─ debit_amount: $0.00
   │   │   └─ credit_amount: $100.00 (full revenue)
   │   │
   │   │   Line 3: Debit Commission Expense
   │   │   ├─ account: 5000 (Commission Expense)
   │   │   ├─ debit_amount: $22.00
   │   │   └─ credit_amount: $0.00
   │   │
   │   │   Line 4: Credit Commission Payable
   │   │   ├─ account: 2000 (Commission Payable)
   │   │   ├─ debit_amount: $0.00
   │   │   └─ credit_amount: $22.00
   │   │
   │   │   Totals: Debit $122.00 = Credit $122.00 ✅
   │   │
   │   └─> Create Revenue Transaction:
   │       ├─ source_type: "mfm_membership"
   │       ├─ source_id: "123" (deposit.id)
   │       ├─ gross_amount: $100.00
   │       ├─ platform_fee: $0.00
   │       ├─ net_amount: $78.00
   │       ├─ affiliate_commissions: $22.00
   │       ├─ transaction_date: timestamp
   │       └─ journal_entry_id: link to journal entry
   │
   │   └─> Commit accounting entries
   │
   ├─> STEP 5.3: ACTIVATE USER SERVICES
   │   │
   │   ├─> Get user from database
   │   │
   │   ├─> Based on product_code:
   │   │   │
   │   │   ├─> "kyc":
   │   │   │   └─> Mark KYC payment as validated
   │   │   │
   │   │   ├─> "mfm_membership" or "efm_membership":
   │   │   │   ├─> user.is_founding_member = True
   │   │   │   └─> user.founding_member_since = now
   │   │   │
   │   │   └─> "annual_membership":
   │   │       └─> Extend membership expiry date
   │   │
   │   └─> Commit user updates
   │
   └─> STEP 5.4: SEND CONFIRMATION EMAIL
       │
       └─> email_service.send_payment_confirmation_email()
           ├─> To: user.email
           ├─> Amount: $100.00
           ├─> Product: "Founding Membership"
           ├─> Reference: tx_hash
           └─> Date: formatted date
   │
   ▼
   
6. RESPONSE TO USER
   │
   └─> Return success response:
       ├─ valid: true
       ├─ deposit_id: 123
       ├─ status: "validated"
       ├─ payer: "0x..."
       └─ tx_hash: "0x..."
```

---

## 📊 Database Records Created

### 1. Deposit Record
```sql
deposits table:
- id: 123
- user_id: 456
- product_type_id: 2
- amount: 100.00
- status: VALIDATED
- order_id: "0x..."
- external_payment_id: "0x..." (tx_hash)
- validated_at: 2026-01-28 10:30:00
```

### 2. Affiliate Commission Records
```sql
affiliate_commissions table:
- id: 1001, user_id: 789, level: 1, commission_amount: 20.00, status: APPROVED
- id: 1002, user_id: 790, level: 2, commission_amount: 2.00, status: APPROVED
```

### 3. Journal Entry
```sql
journal_entries table:
- id: 5001
- entry_number: "JE-20260128-ABC12345"
- entry_date: 2026-01-28 10:30:00
- description: "Payment received - mfm_membership - Deposit #123"
- total_debit: 100.00
- total_credit: 100.00
- status: POSTED
```

### 4. Journal Lines
```sql
journal_lines table:
- Line 1: entry_id: 5001, account_id: 1010, debit: 100.00, credit: 0.00
- Line 2: entry_id: 5001, account_id: 4000, debit: 0.00, credit: 100.00
- Line 3: entry_id: 5001, account_id: 5000, debit: 22.00, credit: 0.00
- Line 4: entry_id: 5001, account_id: 2000, debit: 0.00, credit: 22.00

Total Debit: 122.00 = Total Credit: 122.00 ✅
```

### 5. Revenue Transaction
```sql
revenue_transactions table:
- id: 2001
- source_type: "mfm_membership"
- source_id: "123"
- gross_amount: 100.00
- net_amount: 78.00
- affiliate_commissions: 22.00
- journal_entry_id: 5001
```

---

## 💰 Commission Distribution Examples

### Example 1: KYC Payment ($10)
```
User pays $10 for KYC
├─> Direct Sponsor (Level 1): $2.00
├─> Indirect Sponsor (Level 2): $0.20
├─> Indirect Sponsor (Level 3): $0.20
└─> ... (up to Level 10)

Total Commissions: $2.00 + ($0.20 × 9) = $3.80
Net Revenue: $10.00 - $3.80 = $6.20
```

### Example 2: MFM Membership ($100)
```
User pays $100 for Founding Membership
├─> Direct Sponsor (Level 1): $20.00
├─> Indirect Sponsor (Level 2): $2.00
├─> Indirect Sponsor (Level 3): $2.00
└─> ... (up to Level 10)

Total Commissions: $20.00 + ($2.00 × 9) = $38.00
Net Revenue: $100.00 - $38.00 = $62.00
```

---

## 📝 Accounting Entry Breakdown

### Double-Entry Bookkeeping Rules
- **Debits = Credits** (always balanced)
- **Assets & Expenses**: Increase with Debit
- **Liabilities & Revenue**: Increase with Credit

### Payment Entry Structure
```
DEBIT SIDE (Left):
├─ Crypto Asset: $100.00 (Asset increases)
└─ Commission Expense: $22.00 (Expense increases)
   Total Debit: $122.00

CREDIT SIDE (Right):
├─ Revenue: $78.00 (Revenue increases)
└─ Commission Payable: $22.00 (Liability increases)
   Total Credit: $122.00

Wait... This doesn't balance! ❌

CORRECT ENTRY:
DEBIT:
├─ Crypto Asset: $100.00
└─ Commission Expense: $22.00
   Total: $122.00

CREDIT:
├─ Revenue: $100.00
└─ Commission Payable: $22.00
   Total: $122.00

Actually, the correct accounting is:
DEBIT:
├─ Crypto Asset: $100.00 ✅

CREDIT:
├─ Revenue: $78.00 (net after commissions)
└─ Commission Payable: $22.00
   Total: $100.00 ✅

But wait, this doesn't match either...

ACTUAL IMPLEMENTATION:
DEBIT:
├─ Crypto Asset: $100.00
└─ Commission Expense: $22.00
   Total: $122.00

CREDIT:
├─ Revenue: $78.00
└─ Commission Payable: $22.00
   Total: $100.00

This is WRONG! The entry should be:

CORRECT ACCOUNTING:
DEBIT:
├─ Crypto Asset: $100.00

CREDIT:
├─ Revenue: $100.00

Then separately when commissions are paid:
DEBIT:
├─ Commission Expense: $22.00

CREDIT:
├─ Commission Payable: $22.00

But our implementation combines them, which is also valid:
DEBIT:
├─ Crypto Asset: $100.00
└─ Commission Expense: $22.00
   Total: $122.00

CREDIT:
├─ Revenue: $78.00 (net)
└─ Commission Payable: $22.00
   Total: $100.00

Wait, this still doesn't balance...

CORRECT ACCOUNTING ENTRY:
- Line 1: Debit Crypto Asset: $100.00
- Line 2: Credit Revenue: $100.00 (gross revenue)
- Line 3: Debit Commission Expense: $22.00
- Line 4: Credit Commission Payable: $22.00

Total Debit: $100.00 + $22.00 = $122.00
Total Credit: $100.00 + $22.00 = $122.00 ✅

**Accounting Logic:**
- We record the full payment as revenue (gross)
- Commissions are recorded as an expense and a liability
- When commissions are paid out later, we debit Commission Payable and credit Cash

---

## 🔍 Key Files & Functions

### Backend Files
1. **`backend/app/api/api_v1/endpoints/payments.py`**
   - `create_payment()` - Creates payment order
   - `verify_payment()` - Verifies blockchain transaction

2. **`backend/app/services/commission_distribution.py`**
   - `distribute_commissions()` - Creates affiliate commissions
   - `process_payment_validation()` - Main payment processing

3. **`backend/app/services/accounting_integration.py`** ⭐ NEW
   - `record_payment_in_accounting()` - Creates accounting entries
   - `get_or_create_account()` - Manages chart of accounts

4. **`backend/app/services/onchain_payment.py`**
   - `verify_payment()` - Verifies blockchain transactions

---

## ⚠️ Important Notes

1. **Accounting errors don't block payments**: If accounting entry creation fails, payment still processes successfully
2. **Commissions are auto-approved**: All commissions created have status `APPROVED`
3. **Journal entries are auto-posted**: Payment entries are immediately `POSTED` (not `DRAFT`)
4. **Accounts are auto-created**: If chart of accounts don't exist, they're created automatically
5. **Double-entry is enforced**: All journal entries must balance (debits = credits)

---

## 🐛 Known Issue

The current accounting implementation has a balancing issue. The journal entry totals don't match:
- Total Debit: $122.00
- Total Credit: $100.00

This needs to be fixed to ensure proper double-entry bookkeeping.
