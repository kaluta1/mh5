"""Individual automatic USDT payouts, administrator-approved wallets, KYC commission at payment.

Revision ID: c8e0f2a4b6d8
Revises: b7d9f1a3c5e7
Create Date: 2026-10-18

Owner rules of 2026-10-18. Additive, plus one index narrowed:

* chart_of_accounts: ONE row, 1230 "Deferred affiliate commission cost - KYC"
  (asset, under 1000). A KYC commission is posted when the fee is paid
  (Dr 1230 / Cr 2001) and its cost moves to 5001 when the KYC revenue is
  recognized (Dr 5001 / Cr 1230). Inserted only if missing.
* payout_wallet_approvals: NEW, EMPTY table. One row per wallet a member
  submits; an administrator approves or rejects it; nothing is paid to a
  wallet that is not approved. Self-approval is refused by a CHECK.
* affiliate_cashout_requests: three NULLable columns (commission_id,
  wallet_approval_id, tx_hash) and a unique partial index: at most one open or
  paid payout per commission.
* uq_cashout_one_active_per_user now applies only to payouts of SEVERAL
  commissions (commission_id IS NULL), so each commission can have its own
  payout. Existing rows all have commission_id NULL, so the index covers
  exactly the rows it covered before.
* affiliate_commissions.wallet_notice_at: NULLable; when the member was told
  the commission waits for a payout wallet.

No existing row is changed. Downgrade refuses while any individual payout or
wallet decision exists (a financial record is never destroyed).
"""
from alembic import op

revision = "c8e0f2a4b6d8"
down_revision = "b7d9f1a3c5e7"
branch_labels = None
depends_on = None

ACCOUNT_CODE = "1230"
ACCOUNT_NAME = "Deferred affiliate commission cost - KYC (verification not yet performed)"
DESCRIPTION = ("Direct commission on a paid KYC fee whose verification is not yet performed: Dr 1230, Cr 2001 "
               "when the fee is paid; Dr 5001, Cr 1230 when the KYC revenue is recognized.")


def upgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM chart_of_accounts WHERE account_code = '1000'
                           AND account_type::text = 'ASSET') THEN
                RAISE NOTICE 'asset parent 1000 not found; account {ACCOUNT_CODE} not created';
            ELSE
                INSERT INTO chart_of_accounts (account_code, account_name, account_type, parent_id, balance,
                                               description, is_active, created_at, updated_at)
                SELECT '{ACCOUNT_CODE}', '{ACCOUNT_NAME}', p.account_type, p.id, 0, '{DESCRIPTION}', true, now(), now()
                FROM chart_of_accounts p
                WHERE p.account_code = '1000'
                  AND NOT EXISTS (SELECT 1 FROM chart_of_accounts WHERE account_code = '{ACCOUNT_CODE}');
            END IF;
        END $$""")

    op.execute("""
        CREATE TABLE IF NOT EXISTS payout_wallet_approvals (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            user_id INTEGER NOT NULL REFERENCES users(id),
            address VARCHAR(100) NOT NULL,
            currency VARCHAR(20) NOT NULL,
            status VARCHAR(12) NOT NULL DEFAULT 'PENDING',
            wallet_change_id INTEGER NULL REFERENCES payout_wallet_changes(id),
            submitted_at TIMESTAMP NOT NULL DEFAULT now(),
            verification_method VARCHAR(20) NULL,
            ip_address VARCHAR(45) NULL,
            decided_by INTEGER NULL REFERENCES users(id),
            decided_at TIMESTAMP NULL,
            decision_note VARCHAR(500) NULL,
            superseded_at TIMESTAMP NULL,
            CONSTRAINT ck_payout_wallet_approvals_status
                CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'SUPERSEDED')),
            CONSTRAINT ck_payout_wallet_approvals_not_self
                CHECK (decided_by IS NULL OR decided_by <> user_id)
        )""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payout_wallet_approvals_id ON payout_wallet_approvals (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payout_wallet_approvals_user_id ON payout_wallet_approvals (user_id)")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_payout_wallet_approval_one_pending
                  ON payout_wallet_approvals (user_id) WHERE status = 'PENDING'""")

    op.execute("ALTER TABLE affiliate_cashout_requests "
               "ADD COLUMN IF NOT EXISTS commission_id INTEGER NULL REFERENCES affiliate_commissions(id)")
    op.execute("ALTER TABLE affiliate_cashout_requests "
               "ADD COLUMN IF NOT EXISTS wallet_approval_id INTEGER NULL REFERENCES payout_wallet_approvals(id)")
    op.execute("ALTER TABLE affiliate_cashout_requests ADD COLUMN IF NOT EXISTS tx_hash VARCHAR(150) NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_affiliate_cashout_requests_commission_id "
               "ON affiliate_cashout_requests (commission_id)")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_cashout_commission_live ON affiliate_cashout_requests
                  (commission_id) WHERE commission_id IS NOT NULL
                  AND status IN ('requested', 'processing', 'unknown', 'completed')""")
    op.execute("DROP INDEX IF EXISTS uq_cashout_one_active_per_user")
    op.execute("""CREATE UNIQUE INDEX uq_cashout_one_active_per_user ON affiliate_cashout_requests (user_id)
                  WHERE commission_id IS NULL AND status IN ('requested', 'processing', 'unknown')""")

    op.execute("ALTER TABLE affiliate_commissions ADD COLUMN IF NOT EXISTS wallet_notice_at TIMESTAMP NULL")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM affiliate_cashout_requests WHERE commission_id IS NOT NULL) THEN
                RAISE EXCEPTION 'individual payouts exist; refusing to remove their columns';
            END IF;
            IF EXISTS (SELECT 1 FROM payout_wallet_approvals) THEN
                RAISE EXCEPTION 'payout_wallet_approvals holds records; refusing to drop it';
            END IF;
            IF EXISTS (SELECT 1 FROM journal_lines l JOIN chart_of_accounts a ON a.id = l.account_id
                       WHERE a.account_code = '1230') THEN
                RAISE EXCEPTION 'account 1230 has postings; refusing to downgrade';
            END IF;
        END $$""")
    op.execute("ALTER TABLE affiliate_commissions DROP COLUMN IF EXISTS wallet_notice_at")
    op.execute("DROP INDEX IF EXISTS uq_cashout_one_active_per_user")
    op.execute("""CREATE UNIQUE INDEX uq_cashout_one_active_per_user ON affiliate_cashout_requests (user_id)
                  WHERE status IN ('requested', 'processing', 'unknown')""")
    op.execute("DROP INDEX IF EXISTS uq_cashout_commission_live")
    op.execute("DROP INDEX IF EXISTS ix_affiliate_cashout_requests_commission_id")
    op.execute("ALTER TABLE affiliate_cashout_requests DROP COLUMN IF EXISTS tx_hash")
    op.execute("ALTER TABLE affiliate_cashout_requests DROP COLUMN IF EXISTS wallet_approval_id")
    op.execute("ALTER TABLE affiliate_cashout_requests DROP COLUMN IF EXISTS commission_id")
    op.execute("DROP TABLE IF EXISTS payout_wallet_approvals")
    op.execute(f"DELETE FROM chart_of_accounts WHERE account_code = '{ACCOUNT_CODE}'")
