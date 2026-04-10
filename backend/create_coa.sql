-- Initialisation du Chart of Accounts (Plan Comptable)
-- Correspond à la logique définie dans init_coa.py

-- 1000 - Assets
INSERT INTO chart_of_accounts (account_code, account_name, account_type, is_active, total_liabilities, credit_balance, created_at, updated_at)
VALUES 
    ('1000', 'Assets', 'ASSET', true, 0.0, 0.0, NOW(), NOW()),
    ('1001', 'USDT Treasury (BSC)', 'ASSET', true, 0.0, 0.0, NOW(), NOW()),
    ('1200', 'Accounts Receivable', 'ASSET', true, 0.0, 0.0, NOW(), NOW())
ON CONFLICT (account_code) DO NOTHING;

-- 2000 - Liabilities
INSERT INTO chart_of_accounts (account_code, account_name, account_type, is_active, total_liabilities, credit_balance, created_at, updated_at)
VALUES 
    ('2000', 'Liabilities', 'LIABILITY', true, 0.0, 0.0, NOW(), NOW()),
    ('2001', 'Commissions Payable L1', 'LIABILITY', true, 0.0, 0.0, NOW(), NOW()),
    ('2002', 'Commissions Payable L2-10', 'LIABILITY', true, 0.0, 0.0, NOW(), NOW()),
    ('2003', 'Service Fees Payable (KYC)', 'LIABILITY', true, 0.0, 0.0, NOW(), NOW()),
    ('2100', 'User Funds Payable', 'LIABILITY', true, 0.0, 0.0, NOW(), NOW())
ON CONFLICT (account_code) DO NOTHING;

-- 3000 - Equity
INSERT INTO chart_of_accounts (account_code, account_name, account_type, is_active, total_liabilities, credit_balance, created_at, updated_at)
VALUES 
    ('3000', 'Equity', 'EQUITY', true, 0.0, 0.0, NOW(), NOW()),
    ('3001', 'Retained Earnings', 'EQUITY', true, 0.0, 0.0, NOW(), NOW())
ON CONFLICT (account_code) DO NOTHING;

-- 4000 - Revenue
INSERT INTO chart_of_accounts (account_code, account_name, account_type, is_active, total_liabilities, credit_balance, created_at, updated_at)
VALUES 
    ('4000', 'Revenue', 'REVENUE', true, 0.0, 0.0, NOW(), NOW()),
    ('4001', 'KYC Revenue', 'REVENUE', true, 0.0, 0.0, NOW(), NOW()),
    ('4002', 'Membership Revenue', 'REVENUE', true, 0.0, 0.0, NOW(), NOW())
ON CONFLICT (account_code) DO NOTHING;

-- 5000 - Expenses
INSERT INTO chart_of_accounts (account_code, account_name, account_type, is_active, total_liabilities, credit_balance, created_at, updated_at)
VALUES 
    ('5000', 'Expenses', 'EXPENSE', true, 0.0, 0.0, NOW(), NOW()),
    ('5001', 'Commission Expense', 'EXPENSE', true, 0.0, 0.0, NOW(), NOW()),
    ('5002', 'KYC Provider Expense', 'EXPENSE', true, 0.0, 0.0, NOW(), NOW())
ON CONFLICT (account_code) DO NOTHING;


-- Mise à jour des relations parent-enfant (optionnel, si supporté par la structure)
-- UPDATE chart_of_accounts SET parent_id = (SELECT id FROM chart_of_accounts WHERE account_code = '1000') WHERE account_code IN ('1001', '1200');
-- UPDATE chart_of_accounts SET parent_id = (SELECT id FROM chart_of_accounts WHERE account_code = '2000') WHERE account_code IN ('2001', '2002', '2003', '2100');
-- UPDATE chart_of_accounts SET parent_id = (SELECT id FROM chart_of_accounts WHERE account_code = '3000') WHERE account_code IN ('3001');
-- UPDATE chart_of_accounts SET parent_id = (SELECT id FROM chart_of_accounts WHERE account_code = '4000') WHERE account_code IN ('4001', '4002');
-- UPDATE chart_of_accounts SET parent_id = (SELECT id FROM chart_of_accounts WHERE account_code = '5000') WHERE account_code IN ('5001', '5002');
