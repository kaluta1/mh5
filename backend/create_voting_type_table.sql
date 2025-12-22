-- Script SQL pour créer la table voting_type et ajouter la colonne à contest

-- Créer les types ENUM si ils n'existent pas
DO $$ BEGIN
    CREATE TYPE votinglevel AS ENUM ('city', 'country', 'regional', 'continent', 'global');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE commissionsource AS ENUM ('advert', 'affiliate', 'kyc', 'MFM');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Créer la table voting_type si elle n'existe pas
CREATE TABLE IF NOT EXISTS voting_type (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    voting_level votinglevel NOT NULL,
    commission_rules JSON,
    commission_source commissionsource NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Ajouter la colonne voting_type_id à contest si elle n'existe pas
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest' AND column_name = 'voting_type_id'
    ) THEN
        ALTER TABLE contest ADD COLUMN voting_type_id INTEGER;
    END IF;
END $$;

-- Créer la clé étrangère si elle n'existe pas
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_contest_voting_type'
    ) THEN
        ALTER TABLE contest 
        ADD CONSTRAINT fk_contest_voting_type 
        FOREIGN KEY (voting_type_id) 
        REFERENCES voting_type(id) 
        ON DELETE SET NULL;
    END IF;
END $$;

