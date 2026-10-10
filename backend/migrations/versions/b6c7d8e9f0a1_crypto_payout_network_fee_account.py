"""Chart of accounts: 5005 Crypto payout network fees (paid by MyHigh5).

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-10-10

Additive only: ONE row in chart_of_accounts, approved by the owner on
2026-10-10. It is the expense side of the network fee the payout provider
takes from the USDT treasury (1001) when MyHigh5 bears the fee of a member's
crypto cashout: Dr 5005 / Cr 1001, posted by app/services/cashout_service.py
from the provider's actual fee only.

The row is inserted only if it does not exist and only under the existing
expense parent 5000, whose own account type it copies (the column is a native
enum on some databases and text on others). If account 5000 is missing or is
not an expense account nothing is inserted and a notice is raised: the fee
posting then refuses with "missing accounts: 5005" until the account exists.

No journal entry, commission, cashout or deposit is read or changed.
Downgrade removes the row only if no journal line was ever posted to it.
"""
from alembic import op


revision = "b6c7d8e9f0a1"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None

ACCOUNT_CODE = "5005"
ACCOUNT_NAME = "Crypto payout network fees (paid by MyHigh5)"
DESCRIPTION = ("Network fee the payout provider takes from the USDT treasury when MyHigh5 bears the fee of a "
               "member's crypto cashout: Dr 5005, Cr 1001. Posted from the provider's actual fee only, once per cashout.")


def upgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF to_regclass('public.chart_of_accounts') IS NULL THEN
                RAISE NOTICE 'chart_of_accounts does not exist; account {ACCOUNT_CODE} not created';
            ELSIF NOT EXISTS (SELECT 1 FROM chart_of_accounts
                              WHERE account_code = '5000' AND account_type::text = 'EXPENSE') THEN
                RAISE NOTICE 'expense parent 5000 not found; account {ACCOUNT_CODE} not created';
            ELSE
                INSERT INTO chart_of_accounts (account_code, account_name, account_type, parent_id, balance,
                                               description, is_active, created_at, updated_at)
                SELECT '{ACCOUNT_CODE}', '{ACCOUNT_NAME}', p.account_type, p.id, 0, '{DESCRIPTION.replace("'", "''")}',
                       true, now(), now()
                FROM chart_of_accounts p
                WHERE p.account_code = '5000'
                  AND NOT EXISTS (SELECT 1 FROM chart_of_accounts WHERE account_code = '{ACCOUNT_CODE}');
            END IF;
        END $$""")


def downgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF to_regclass('public.chart_of_accounts') IS NOT NULL THEN
                DELETE FROM chart_of_accounts a
                WHERE a.account_code = '{ACCOUNT_CODE}'
                  AND NOT EXISTS (SELECT 1 FROM journal_lines l WHERE l.account_id = a.id);
            END IF;
        END $$""")
