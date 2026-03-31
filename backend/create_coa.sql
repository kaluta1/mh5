-- Canonical MyHigh5 chart of accounts seed.
-- Keep this in sync with backend/app/services/accounting_posting.py.
-- The Python seed remains the source of truth because it can safely update
-- parents, names, descriptions, active flags, and reporting metadata in-place.

ALTER TABLE chart_of_accounts
    ADD COLUMN IF NOT EXISTS normal_balance VARCHAR(10) NOT NULL DEFAULT 'debit',
    ADD COLUMN IF NOT EXISTS statement_section VARCHAR(50),
    ADD COLUMN IF NOT EXISTS report_group VARCHAR(100),
    ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS is_contra_account BOOLEAN NOT NULL DEFAULT FALSE;

WITH payload (
    account_code,
    account_name,
    account_type,
    parent_code,
    description,
    normal_balance,
    statement_section,
    report_group,
    sort_order,
    is_contra_account
) AS (
    VALUES
        ('1000', 'Current Assets', 'ASSET'::accounttype, NULL::text, 'Top-level current asset accounts.', 'debit', 'current_asset', 'Current Assets', 1000, FALSE),
        ('1010', 'Operating Cash / USDT Treasury', 'ASSET'::accounttype, '1000', 'Operating cash and on-platform treasury balances.', 'debit', 'current_asset', 'Cash and Cash Equivalents', 1010, FALSE),
        ('1020', 'Processor Clearing Receivable', 'ASSET'::accounttype, '1000', 'Amounts validated but still clearing from payment processors.', 'debit', 'current_asset', 'Receivables', 1020, FALSE),
        ('1030', 'Restricted / Frozen Funds', 'ASSET'::accounttype, '1000', 'Crypto or other funds validated but not yet released to operating treasury.', 'debit', 'current_asset', 'Restricted Funds', 1030, FALSE),
        ('1040', 'Affiliate / Other Receivables', 'ASSET'::accounttype, '1000', 'Receivables owed to the platform outside processor settlement.', 'debit', 'current_asset', 'Receivables', 1040, FALSE),
        ('2000', 'Current Liabilities', 'LIABILITY'::accounttype, NULL::text, 'Top-level current liability accounts.', 'credit', 'current_liability', 'Current Liabilities', 2000, FALSE),
        ('2010', 'User Wallet Liability', 'LIABILITY'::accounttype, '2000', 'Amounts owed to users in their platform wallets.', 'credit', 'current_liability', 'Wallet and User Balances', 2010, FALSE),
        ('2020', 'Affiliate Commission Payable', 'LIABILITY'::accounttype, '2000', 'Approved affiliate commissions awaiting settlement.', 'credit', 'current_liability', 'Payables', 2020, FALSE),
        ('2030', 'Prize Payable', 'LIABILITY'::accounttype, '2000', 'Prize obligations accrued before wallet credit or cash payment.', 'credit', 'current_liability', 'Payables', 2030, FALSE),
        ('2040', 'Sales Tax / VAT Payable', 'LIABILITY'::accounttype, '2000', 'Indirect taxes collected and not yet remitted.', 'credit', 'current_liability', 'Taxes', 2040, FALSE),
        ('2050', 'KYC Vendor Payable', 'LIABILITY'::accounttype, '2000', 'Amounts owed to KYC verification providers.', 'credit', 'current_liability', 'Payables', 2050, FALSE),
        ('2060', 'Deferred Membership Revenue', 'LIABILITY'::accounttype, '2000', 'Membership cash collected before earning over the service period.', 'credit', 'current_liability', 'Deferred Revenue', 2060, FALSE),
        ('2070', 'Deferred Service Revenue', 'LIABILITY'::accounttype, '2000', 'Service cash collected before the underlying obligation is satisfied.', 'credit', 'current_liability', 'Deferred Revenue', 2070, FALSE),
        ('3000', 'Equity', 'EQUITY'::accounttype, NULL::text, 'Top-level equity accounts.', 'credit', 'equity', 'Equity', 3000, FALSE),
        ('3100', 'Retained Earnings', 'EQUITY'::accounttype, '3000', 'Accumulated profit retained in the business.', 'credit', 'equity', 'Retained Earnings', 3100, FALSE),
        ('4000', 'Revenue', 'REVENUE'::accounttype, NULL::text, 'Top-level revenue accounts.', 'credit', 'revenue', 'Revenue', 4000, FALSE),
        ('4010', 'KYC Revenue', 'REVENUE'::accounttype, '4000', 'Recognized revenue from KYC services.', 'credit', 'revenue', 'Service Revenue', 4010, FALSE),
        ('4020', 'Membership Revenue Recognized', 'REVENUE'::accounttype, '4000', 'Recognized membership revenue released from deferred revenue.', 'credit', 'revenue', 'Membership Revenue', 4020, FALSE),
        ('4030', 'Contest Entry Revenue', 'REVENUE'::accounttype, '4000', 'Recognized contest entry fees.', 'credit', 'revenue', 'Contest Revenue', 4030, FALSE),
        ('4040', 'Advertising Revenue', 'REVENUE'::accounttype, '4000', 'Recognized advertising and sponsorship revenue.', 'credit', 'revenue', 'Advertising Revenue', 4040, FALSE),
        ('4050', 'Club Revenue', 'REVENUE'::accounttype, '4000', 'Recognized fan club and membership revenue outside core subscriptions.', 'credit', 'revenue', 'Club Revenue', 4050, FALSE),
        ('4060', 'Shop / Other Revenue', 'REVENUE'::accounttype, '4000', 'Recognized non-core revenue streams.', 'credit', 'revenue', 'Other Revenue', 4060, FALSE),
        ('4090', 'Sales Returns / Refund Contra-Revenue', 'REVENUE'::accounttype, '4000', 'Refunds tied directly to revenue-producing sales.', 'debit', 'contra_revenue', 'Contra Revenue', 4090, TRUE),
        ('5000', 'Cost of Sales / Direct Costs', 'EXPENSE'::accounttype, NULL::text, 'Top-level direct cost accounts.', 'debit', 'direct_cost', 'Cost of Sales', 5000, FALSE),
        ('5010', 'KYC Provider Fees', 'EXPENSE'::accounttype, '5000', 'Direct vendor fees for identity verification.', 'debit', 'direct_cost', 'Service Delivery Costs', 5010, FALSE),
        ('5020', 'Prize Expense Recognized', 'EXPENSE'::accounttype, '5000', 'Prize expense recognized when winner obligations are accrued.', 'debit', 'direct_cost', 'Contest Costs', 5020, FALSE),
        ('5030', 'Payment / Payout Processing Fees', 'EXPENSE'::accounttype, '5000', 'Direct processor and payout fees.', 'debit', 'direct_cost', 'Processing Costs', 5030, FALSE),
        ('6000', 'Operating Expenses', 'EXPENSE'::accounttype, NULL::text, 'Top-level operating expense accounts.', 'debit', 'operating_expense', 'Operating Expenses', 6000, FALSE),
        ('6010', 'Affiliate Commission Expense', 'EXPENSE'::accounttype, '6000', 'Affiliate commission expense recognized on qualifying revenue.', 'debit', 'operating_expense', 'Sales and Marketing', 6010, FALSE),
        ('6020', 'Platform Operations Expense', 'EXPENSE'::accounttype, '6000', 'General platform operating and administrative costs.', 'debit', 'operating_expense', 'General and Administrative', 6020, FALSE),
        ('6030', 'Non-Sales Refund / Adjustment Expense', 'EXPENSE'::accounttype, '6000', 'Refunds and adjustments not tied directly to a revenue stream.', 'debit', 'operating_expense', 'General and Administrative', 6030, FALSE),
        ('6040', 'FX Gain / Loss', 'EXPENSE'::accounttype, '6000', 'Foreign exchange remeasurement gains or losses.', 'debit', 'other_gain_loss', 'FX and Other', 6040, FALSE)
)
INSERT INTO chart_of_accounts (
    account_code,
    account_name,
    account_type,
    parent_id,
    description,
    is_active,
    total_liabilities,
    credit_balance,
    normal_balance,
    statement_section,
    report_group,
    sort_order,
    is_contra_account,
    created_at,
    updated_at
)
SELECT payload.account_code,
       payload.account_name,
       payload.account_type,
       parent.id,
       payload.description,
       TRUE,
       0,
       0,
       payload.normal_balance,
       payload.statement_section,
       payload.report_group,
       payload.sort_order,
       payload.is_contra_account,
       NOW(),
       NOW()
FROM payload
LEFT JOIN chart_of_accounts parent ON parent.account_code = payload.parent_code
ON CONFLICT (account_code)
DO UPDATE SET
    account_name = EXCLUDED.account_name,
    account_type = EXCLUDED.account_type,
    parent_id = EXCLUDED.parent_id,
    description = EXCLUDED.description,
    is_active = TRUE,
    normal_balance = EXCLUDED.normal_balance,
    statement_section = EXCLUDED.statement_section,
    report_group = EXCLUDED.report_group,
    sort_order = EXCLUDED.sort_order,
    is_contra_account = EXCLUDED.is_contra_account,
    updated_at = NOW();
