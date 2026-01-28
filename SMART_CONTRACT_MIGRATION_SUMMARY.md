# Smart Contract Payment Migration Summary

## ✅ Completed Changes

### Backend Changes

1. **Removed NowPayments Integration**
   - ✅ Deleted `backend/app/services/crypto_payment.py`
   - ✅ Removed NowPayments config from `backend/app/core/config.py`
   - ✅ Updated `backend/app/services/payment_scheduler.py` to remove crypto_payment references

2. **Added Smart Contract Payment System**
   - ✅ Created `backend/app/services/onchain_payment.py` - BSC smart contract payment verification service
   - ✅ Updated `backend/app/core/config.py` with:
     - BSC network configuration (RPC URL, Chain ID, Contract addresses)
     - Reown Project ID configuration
     - USDT token configuration

3. **Updated Payment Endpoints** (`backend/app/api/api_v1/endpoints/payments.py`)
   - ✅ `/create` - Creates payment order with order_id (bytes32)
   - ✅ `/verify` - Verifies payment using transaction hash
   - ✅ `/check/{deposit_id}` - Checks payment status
   - ✅ `/check-status/{deposit_id}` - Gets payment details
   - ✅ Removed `/invoice` endpoint (not needed for smart contracts)
   - ✅ Removed `/webhook` endpoint (payments verified on-chain)
   - ✅ Removed `/currencies` endpoint (only USDT supported)
   - ✅ Removed `/estimate` endpoint (not needed)

### Frontend Changes

1. **Configuration Files**
   - ✅ Updated `frontend/lib/config.ts` with:
     - Reown Project ID configuration
     - Contract addresses and network configuration
   - ✅ Created `frontend/lib/contracts.ts` with:
     - Payment contract ABI
     - ERC20 token ABI
     - Contract addresses
     - Network configuration

2. **Wallet Integration**
   - ✅ Created `frontend/lib/wallet.ts` - Reown WalletConnect provider setup

3. **Payment Service**
   - ✅ Updated `frontend/services/payment-service.ts`:
     - Updated interfaces to match new API
     - Removed invoice-related methods
     - Added `verifyPayment()` method
     - Updated `createPayment()` to return smart contract details

4. **Dependencies**
   - ✅ Added to `frontend/package.json`:
     - `@walletconnect/ethereum-provider`: "^2.23.4"
     - `ethers`: "^6.16.0"

## 📋 Required Next Steps

### 1. Install Frontend Dependencies

```bash
cd frontend
npm install
```

This will install:
- `@walletconnect/ethereum-provider` - For Reown/WalletConnect integration
- `ethers` - For Ethereum/BSC blockchain interactions

### 2. Set Environment Variables

**Backend `.env` file:**
```env
# BSC Smart Contract Payment Configuration
BSC_PAYMENT_CONTRACT=0xed8cbdFEB6104A49edCe79666Aae66Eda0d3b622
BSC_USDT_ADDRESS=0x55d398326f99059fF775485246999027B3197955
BSC_USDT_DECIMALS=18
BSC_RPC_URL=https://bsc-dataseed.binance.org
BSC_CHAIN_ID=56
BSC_CONFIRMATIONS=1
BSC_EXPLORER_URL=https://bscscan.com

# Reown/WalletConnect Configuration
REOWN_PROJECT_ID=your_reown_project_id_here
```

**Frontend `.env.local` file:**
```env
NEXT_PUBLIC_REOWN_PROJECT_ID=your_reown_project_id_here
```

### 3. Get Reown Project ID

1. Go to https://cloud.reown.com
2. Sign up or log in
3. Create a new project or select existing
4. Copy your Project ID
5. Add it to both backend `.env` and frontend `.env.local`

### 4. Update Payment Dialogs

The payment dialog components need to be updated to:
- Connect wallet using Reown/MetaMask
- Execute smart contract payment using ethers.js
- Submit transaction hash for verification

**Files to update:**
- `frontend/components/dialogs/payment-dialog.tsx`
- `frontend/components/dialogs/payment-dialog-v2.tsx`

**Example payment flow:**
```typescript
// 1. Connect wallet
const provider = await connectWallet() // MetaMask or Reown
const signer = await provider.getSigner()

// 2. Get payment order from API
const payment = await paymentService.createPayment(token, {
  amount: 100,
  currency: 'usd',
  product_code: 'kyc'
})

// 3. Approve USDT if needed
const tokenContract = new Contract(USDT_ADDRESS, ERC20_ABI, signer)
const allowance = await tokenContract.allowance(address, PAYMENT_CONTRACT)
if (allowance < payment.amount_wei) {
  await tokenContract.approve(PAYMENT_CONTRACT, payment.amount_wei)
}

// 4. Execute payment
const paymentContract = new Contract(PAYMENT_CONTRACT, PAYMENT_ABI, signer)
const tx = await paymentContract.payToken(
  payment.order_id,
  payment.token_address,
  payment.amount_wei
)
const receipt = await tx.wait()

// 5. Verify payment
await paymentService.verifyPayment(token, {
  order_id: payment.order_id,
  tx_hash: receipt.hash
})
```

### 5. Verify Backend Dependencies

The backend already has `requests` in requirements.txt, which is needed for the onchain payment service.

## 🔍 Contract Details

### Payment Contract
- **Address**: `0xed8cbdFEB6104A49edCe79666Aae66Eda0d3b622`
- **Network**: BSC Mainnet (Chain ID: 56)
- **Functions**:
  - `payNative(bytes32 orderId)` - For BNB payments
  - `payToken(bytes32 orderId, address token, uint256 amount)` - For USDT payments

### USDT Token
- **Address**: `0x55d398326f99059fF775485246999027B3197955`
- **Decimals**: 18
- **Standard**: ERC20

## ⚠️ Important Notes

1. **Payment Verification**: Payments are verified on-chain by checking transaction receipts and events. No webhooks needed.

2. **Order ID Format**: Order IDs are bytes32 (0x + 64 hex characters) generated by the backend.

3. **Transaction Confirmation**: The backend checks for at least 1 confirmation (configurable via `BSC_CONFIRMATIONS`).

4. **Error Handling**: All payment errors are now properly logged and return user-friendly error messages.

5. **Backward Compatibility**: Old NowPayments deposits will remain in the database but new payments will use smart contracts.

## 🧪 Testing Checklist

- [ ] Install frontend dependencies (`npm install`)
- [ ] Set environment variables (backend and frontend)
- [ ] Get Reown Project ID and configure
- [ ] Test wallet connection (MetaMask/Reown)
- [ ] Test payment creation API endpoint
- [ ] Test payment execution on BSC testnet (if available)
- [ ] Test payment verification API endpoint
- [ ] Update payment dialog UI components
- [ ] Test full payment flow end-to-end

## 📚 Documentation

See the original configuration document for:
- Complete contract ABIs
- Detailed setup instructions
- Code examples
- Troubleshooting guide
