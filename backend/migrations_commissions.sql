-- 1. Mettre à jour le type ENUM commissiontype
-- Utilisation de blocs transactionnels pour éviter les erreurs si la valeur existe déjà (PostgreSQL 9.1+)
-- Note: 'ALTER TYPE ... ADD VALUE' ne peut pas être exécuté dans un bloc de transaction normal
-- Ces commandes doivent être exécutées individuellement si le script échoue tout d'un bloc.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid  
                   WHERE t.typname = 'commissiontype' AND e.enumlabel = 'KYC_PAYMENT') THEN
        ALTER TYPE commissiontype ADD VALUE 'KYC_PAYMENT';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid  
                   WHERE t.typname = 'commissiontype' AND e.enumlabel = 'FOUNDING_MEMBERSHIP_FEE') THEN
        ALTER TYPE commissiontype ADD VALUE 'FOUNDING_MEMBERSHIP_FEE';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid  
                   WHERE t.typname = 'commissiontype' AND e.enumlabel = 'ANNUAL_MEMBERSHIP_FEE') THEN
        ALTER TYPE commissiontype ADD VALUE 'ANNUAL_MEMBERSHIP_FEE';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid  
                   WHERE t.typname = 'commissiontype' AND e.enumlabel = 'EFM_MEMBERSHIP') THEN
        ALTER TYPE commissiontype ADD VALUE 'EFM_MEMBERSHIP';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid  
                   WHERE t.typname = 'commissiontype' AND e.enumlabel = 'MONTHLY_REVENUE_POOL') THEN
        ALTER TYPE commissiontype ADD VALUE 'MONTHLY_REVENUE_POOL';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid  
                   WHERE t.typname = 'commissiontype' AND e.enumlabel = 'ANNUAL_PROFIT_POOL') THEN
        ALTER TYPE commissiontype ADD VALUE 'ANNUAL_PROFIT_POOL';
    END IF;
END $$;

-- 2. Créer la table commission_rules
CREATE TABLE IF NOT EXISTS commission_rules (
    id SERIAL PRIMARY KEY,
    product_code VARCHAR(50) NOT NULL UNIQUE,
    commission_type commissiontype NOT NULL, 
    direct_percentage NUMERIC(5, 2) DEFAULT 10.0,
    indirect_percentage NUMERIC(5, 2) DEFAULT 1.0,
    max_levels INTEGER DEFAULT 10,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
);

-- Index pour les performances
CREATE INDEX IF NOT EXISTS ix_commission_rules_product_code ON commission_rules (product_code);

-- 3. Insérer les règles par défaut
INSERT INTO commission_rules (product_code, commission_type, direct_percentage, indirect_percentage, max_levels, is_active)
VALUES 
    ('kyc', 'KYC_PAYMENT', 10.00, 1.00, 10, true),
    ('mfm_membership', 'FOUNDING_MEMBERSHIP_FEE', 10.00, 1.00, 10, true),
    ('annual_membership', 'ANNUAL_MEMBERSHIP_FEE', 10.00, 1.00, 10, true),
    ('efm_membership', 'EFM_MEMBERSHIP', 10.00, 1.00, 10, true)
ON CONFLICT (product_code) DO NOTHING;
