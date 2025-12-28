-- Add affiliate_agreement_accepted and affiliate_agreement_accepted_at columns to users table

-- Add affiliate_agreement_accepted column
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'affiliate_agreement_accepted'
    ) THEN
        ALTER TABLE users
        ADD COLUMN affiliate_agreement_accepted BOOLEAN DEFAULT false NOT NULL;
    END IF;
END $$;

-- Add affiliate_agreement_accepted_at column
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'affiliate_agreement_accepted_at'
    ) THEN
        ALTER TABLE users
        ADD COLUMN affiliate_agreement_accepted_at TIMESTAMP;
    END IF;
END $$;

