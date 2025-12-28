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

-- Ajouter la colonne is_deleted à contest_seasons si elle n'existe pas
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest_seasons' AND column_name = 'is_deleted'
    ) THEN
        ALTER TABLE contest_seasons ADD COLUMN is_deleted BOOLEAN DEFAULT false NOT NULL;
    END IF;
END $$;

-- Ajouter la colonne created_at à contest_seasons si elle n'existe pas
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest_seasons' AND column_name = 'created_at'
    ) THEN
        ALTER TABLE contest_seasons ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
    END IF;
END $$;

-- Ajouter la colonne updated_at à contest_seasons si elle n'existe pas
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest_seasons' AND column_name = 'updated_at'
    ) THEN
        ALTER TABLE contest_seasons ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
    END IF;
END $$;

-- Supprimer les colonnes obsolètes qui ne sont plus dans le modèle
DO $$ BEGIN
    ALTER TABLE contest_seasons DROP COLUMN IF EXISTS registration_start;
    ALTER TABLE contest_seasons DROP COLUMN IF EXISTS registration_end;
    ALTER TABLE contest_seasons DROP COLUMN IF EXISTS contest_type_id;
    ALTER TABLE contest_seasons DROP COLUMN IF EXISTS year;
    ALTER TABLE contest_seasons DROP COLUMN IF EXISTS season_number;
    ALTER TABLE contest_seasons DROP COLUMN IF EXISTS status;
    ALTER TABLE contest_seasons DROP COLUMN IF EXISTS start_date;
    ALTER TABLE contest_seasons DROP COLUMN IF EXISTS end_date;
    ALTER TABLE contest_seasons DROP COLUMN IF EXISTS upload_end_date;
EXCEPTION WHEN undefined_column THEN null;
END $$;

-- Convertir contest.level de ENUM à VARCHAR(20) si c'est encore un ENUM
DO $$ 
BEGIN 
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest' 
        AND column_name = 'level'
        AND udt_name = 'contest_level'
    ) THEN
        ALTER TABLE contest ALTER COLUMN level TYPE VARCHAR(20) USING level::text;
        
        -- Supprimer le type ENUM s'il n'est plus utilisé
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE udt_name = 'contest_level'
        ) THEN
            DROP TYPE IF EXISTS contest_level;
        END IF;
    END IF;
EXCEPTION WHEN OTHERS THEN
    NULL;
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

-- Vérifier que les colonnes title, is_deleted, created_at et updated_at existent dans contest_seasons
SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'contest_seasons' 
AND column_name IN ('title', 'is_deleted', 'created_at', 'updated_at')
ORDER BY column_name;

