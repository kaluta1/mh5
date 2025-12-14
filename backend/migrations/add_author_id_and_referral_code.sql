-- Script SQL pour ajouter author_id et referral_code à contestant_shares
-- À exécuter manuellement si la migration Alembic ne fonctionne pas

-- Ajouter la colonne author_id
ALTER TABLE contestant_shares 
ADD COLUMN IF NOT EXISTS author_id INTEGER;

-- Ajouter la contrainte de clé étrangère
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'fk_contestant_shares_author_id'
    ) THEN
        ALTER TABLE contestant_shares
        ADD CONSTRAINT fk_contestant_shares_author_id
        FOREIGN KEY (author_id) REFERENCES users(id);
    END IF;
END $$;

-- Créer l'index
CREATE INDEX IF NOT EXISTS ix_contestant_shares_author_id ON contestant_shares(author_id);

-- Ajouter la colonne referral_code
ALTER TABLE contestant_shares 
ADD COLUMN IF NOT EXISTS referral_code VARCHAR(50);

-- Migrer les données : copier user_id vers author_id si user_id existe
UPDATE contestant_shares
SET author_id = user_id
WHERE user_id IS NOT NULL AND author_id IS NULL;

