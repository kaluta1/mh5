-- 1. Balance Sheet Query (Actif / Passif / Equity)
-- Assets = Liabilities + Equity
SELECT 
    ca.account_type,
    ca.account_code,
    ca.account_name,
    SUM(jl.debit_amount) as total_debit,
    SUM(jl.credit_amount) as total_credit,
    CASE 
        WHEN ca.account_type::text IN ('ASSET', 'EXPENSE', 'asset', 'expense') THEN SUM(jl.debit_amount) - SUM(jl.credit_amount)
        ELSE SUM(jl.credit_amount) - SUM(jl.debit_amount)
    END as balance
FROM journal_lines jl
JOIN chart_of_accounts ca ON jl.account_id = ca.id
WHERE ca.account_type::text IN ('ASSET', 'LIABILITY', 'EQUITY', 'asset', 'liability', 'equity') -- Tentative de support des deux cas ou juste Uppercase
GROUP BY ca.account_type, ca.account_code, ca.account_name
ORDER BY ca.account_code;

-- 2. Profit & Loss (Income Statement)
-- Net Income = Revenue - Expenses
SELECT 
    ca.account_type,
    ca.account_code,
    ca.account_name,
    SUM(jl.debit_amount) as total_debit,
    SUM(jl.credit_amount) as total_credit,
    CASE 
        WHEN ca.account_type::text IN ('ASSET', 'EXPENSE', 'asset', 'expense') THEN SUM(jl.debit_amount) - SUM(jl.credit_amount)
        ELSE SUM(jl.credit_amount) - SUM(jl.debit_amount)
    END as net_change
FROM journal_lines jl
JOIN chart_of_accounts ca ON jl.account_id = ca.id
WHERE ca.account_type::text IN ('REVENUE', 'EXPENSE', 'revenue', 'expense')
GROUP BY ca.account_type, ca.account_code, ca.account_name
ORDER BY ca.account_code;

-- 3. User Commission Balance (Sub-ledger view)
-- Récupérer le solde dû à chaque utilisateur (Liabilities Accounts)
SELECT 
    jl.account_id,
    ca.account_name,
    SUM(jl.credit_amount) - SUM(jl.debit_amount) as payable_balance
FROM journal_lines jl
JOIN chart_of_accounts ca ON jl.account_id = ca.id
WHERE ca.account_type::text IN ('LIABILITY', 'liability')
AND ca.account_code LIKE '20%' -- Comptes starting with 20 (Commissions Payable)
GROUP BY jl.account_id, ca.account_name;
