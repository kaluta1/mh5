-- Canonical MyHigh5 chart of accounts seed.
-- Keep this in sync with backend/app/services/accounting_posting.py.
-- The Python seed remains the source of truth because it can safely update
-- parents, names, descriptions, and active flags in-place.

INSERT INTO chart_of_accounts (account_code, account_name, account_type, parent_id, description, is_active, total_liabilities, credit_balance, created_at, updated_at)
SELECT payload.account_code,
       payload.account_name,
       payload.account_type,
       parent.id,
       payload.description,
       TRUE,
       0,
       0,
       NOW(),
       NOW()
FROM (
    VALUES
        ('1000', 'Assets', 'ASSET', NULL, 'Top-level asset accounts.'),
        ('1010', 'Platform Cash / USDT Wallet', 'ASSET', '1000', 'Cash or stablecoin balances controlled by the platform.'),
        ('1020', 'Payment Provider Receivables', 'ASSET', '1000', 'Validated amounts expected from processors before settlement.'),
        ('1030', 'Restricted / Frozen Funds', 'ASSET', '1000', 'Funds held but not available for general use.'),
        ('2000', 'Liabilities', 'LIABILITY', NULL, 'Top-level liability accounts.'),
        ('2010', 'User Wallet Liability', 'LIABILITY', '2000', 'Amounts owed to users inside platform wallets.'),
        ('2020', 'Affiliate Commission Payable', 'LIABILITY', '2000', 'Approved commissions owed to affiliates until settled.'),
        ('2030', 'Prize Payable', 'LIABILITY', '2000', 'Prize obligations awaiting settlement.'),
        ('2040', 'Tax Payable', 'LIABILITY', '2000', 'Taxes collected or accrued and not yet remitted.'),
        ('2050', 'KYC Provider Payable', 'LIABILITY', '2000', 'Amounts owed to KYC vendors for completed checks.'),
        ('2060', 'Deferred Revenue', 'LIABILITY', '2000', 'Cash received before revenue recognition where deferral is required.'),
        ('3000', 'Equity', 'EQUITY', NULL, 'Top-level equity accounts.'),
        ('3100', 'Retained Earnings', 'EQUITY', '3000', 'Accumulated earnings retained in the business.'),
        ('4000', 'Revenue', 'REVENUE', NULL, 'Top-level revenue accounts.'),
        ('4010', 'KYC Revenue', 'REVENUE', '4000', 'Revenue from KYC purchases.'),
        ('4020', 'Membership Revenue', 'REVENUE', '4000', 'Revenue from memberships and renewals.'),
        ('4030', 'Contest Entry Fee Revenue', 'REVENUE', '4000', 'Revenue from contest participation fees.'),
        ('4040', 'Advertising Revenue', 'REVENUE', '4000', 'Revenue from ads and sponsorship inventory.'),
        ('4050', 'Club Revenue', 'REVENUE', '4000', 'Revenue from clubs or memberships outside core subscriptions.'),
        ('4060', 'Shop / Other Revenue', 'REVENUE', '4000', 'Catch-all non-core earned revenue.'),
        ('5000', 'Direct Costs', 'EXPENSE', NULL, 'Top-level direct cost accounts.'),
        ('5010', 'KYC Provider Fees', 'EXPENSE', '5000', 'Direct vendor costs for identity verification.'),
        ('5020', 'Prize Payout Expense', 'EXPENSE', '5000', 'Direct contest prize costs recognized when awarded.'),
        ('5030', 'Payout Processing Fees', 'EXPENSE', '5000', 'Direct payment or payout processing fees.'),
        ('6000', 'Operating Expenses', 'EXPENSE', NULL, 'Top-level operating expense accounts.'),
        ('6010', 'Affiliate Commission Expense', 'EXPENSE', '6000', 'Affiliate commission expense recognized on qualifying revenue.'),
        ('6020', 'Platform Operations Expense', 'EXPENSE', '6000', 'General operating costs and adjustments.'),
        ('6030', 'Refunds and Charge Adjustments', 'EXPENSE', '6000', 'Refunds, reversals, and charge adjustments.')
) AS payload(account_code, account_name, account_type, parent_code, description)
LEFT JOIN chart_of_accounts parent ON parent.account_code = payload.parent_code
ON CONFLICT (account_code)
DO UPDATE SET
    account_name = EXCLUDED.account_name,
    account_type = EXCLUDED.account_type,
    parent_id = EXCLUDED.parent_id,
    description = EXCLUDED.description,
    is_active = TRUE,
    updated_at = NOW();
