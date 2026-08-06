-- Run in Neon Dashboard → SQL Editor (runs as database owner).
-- Fixes: alembic "must be owner of table users" when VPS DATABASE_URL uses a non-owner role.
-- Safe to re-run (IF NOT EXISTS / IF NOT EXISTS patterns).

-- ---------------------------------------------------------------------------
-- r2s3t4u5v6w7 — affiliate payout wallet
-- ---------------------------------------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS usdt_wallet_address VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS payout_currency VARCHAR(20) DEFAULT 'usdtbsc';
ALTER TABLE affiliate_commissions ADD COLUMN IF NOT EXISTS payout_reference VARCHAR(255);

CREATE TABLE IF NOT EXISTS affiliate_cashout_requests (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    user_id INTEGER NOT NULL REFERENCES users(id),
    gross_amount NUMERIC(10, 2) NOT NULL,
    fee NUMERIC(10, 2) NOT NULL DEFAULT 0,
    net_amount NUMERIC(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'processing',
    payout_method VARCHAR(30) DEFAULT 'nowpayments_crypto',
    wallet_snapshot VARCHAR(100),
    payout_reference VARCHAR(255),
    requested_at TIMESTAMP NOT NULL DEFAULT now(),
    processed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_affiliate_cashout_requests_user_id
    ON affiliate_cashout_requests (user_id);

-- ---------------------------------------------------------------------------
-- s3t4u5v6w7x8 — Kaluta KYC provider enum value
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'verificationprovider') THEN
        ALTER TYPE verificationprovider ADD VALUE IF NOT EXISTS 'kaluta';
    END IF;
END$$;

-- ---------------------------------------------------------------------------
-- KYC proof-of-address status (if missing)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'kycstatus') THEN
        ALTER TYPE kycstatus ADD VALUE IF NOT EXISTS 'PENDING_PROOF_OF_ADDRESS';
    END IF;
END$$;

-- ---------------------------------------------------------------------------
-- Mark alembic revisions applied (only if alembic_version table exists)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'alembic_version'
    ) THEN
        UPDATE alembic_version SET version_num = 's3t4u5v6w7x8'
        WHERE version_num = 'q1r2s3t4u5v6';
        IF NOT FOUND THEN
            INSERT INTO alembic_version (version_num)
            SELECT 's3t4u5v6w7x8'
            WHERE NOT EXISTS (SELECT 1 FROM alembic_version);
        END IF;
    END IF;
END$$;
