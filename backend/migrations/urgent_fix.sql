-- Script SQL d'urgence pour ajouter les colonnes manquantes
-- À exécuter directement dans la base de données PostgreSQL

-- Créer les ENUM types si ils n'existent pas
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
    commission_rules JSONB,
    commission_source commissionsource NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Ajouter les colonnes manquantes à la table contest
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest' AND column_name = 'cover_image_url'
    ) THEN
        ALTER TABLE contest ADD COLUMN cover_image_url VARCHAR(500);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest' AND column_name = 'voting_type_id'
    ) THEN
        ALTER TABLE contest ADD COLUMN voting_type_id INTEGER;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest' AND column_name = 'is_deleted'
    ) THEN
        ALTER TABLE contest ADD COLUMN is_deleted BOOLEAN DEFAULT false NOT NULL;
    END IF;
END $$;

-- Ajouter la contrainte de clé étrangère si elle n'existe pas
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_contest_voting_type'
    ) THEN
        ALTER TABLE contest 
        ADD CONSTRAINT fk_contest_voting_type 
        FOREIGN KEY (voting_type_id) REFERENCES voting_type(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Ajouter la colonne title à contest_seasons si elle n'existe pas
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest_seasons' AND column_name = 'title'
    ) THEN
        ALTER TABLE contest_seasons ADD COLUMN title VARCHAR(200);
        UPDATE contest_seasons SET title = 'Saison sans titre' WHERE title IS NULL;
        ALTER TABLE contest_seasons ALTER COLUMN title SET NOT NULL;
    END IF;
END $$;

-- Vérifier que les colonnes ont été ajoutées
SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'contest' 
AND column_name IN ('cover_image_url', 'voting_type_id', 'is_deleted')
ORDER BY column_name;

-- Vérifier que la colonne title existe dans contest_seasons
SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'contest_seasons' 
AND column_name = 'title';

