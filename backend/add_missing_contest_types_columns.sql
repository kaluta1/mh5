-- Script pour ajouter les colonnes manquantes à la table contest_types
-- À exécuter sur Render via la console SQL de PostgreSQL

-- Ajouter la colonne rules si elle n'existe pas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest_types' AND column_name = 'rules'
    ) THEN
        ALTER TABLE contest_types ADD COLUMN rules TEXT;
        RAISE NOTICE 'Colonne rules ajoutée à contest_types';
    ELSE
        RAISE NOTICE 'Colonne rules existe déjà dans contest_types';
    END IF;
END $$;

-- Ajouter la colonne voting_restriction si elle n'existe pas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest_types' AND column_name = 'voting_restriction'
    ) THEN
        ALTER TABLE contest_types ADD COLUMN voting_restriction VARCHAR(20) DEFAULT 'none';
        RAISE NOTICE 'Colonne voting_restriction ajoutée à contest_types';
    ELSE
        RAISE NOTICE 'Colonne voting_restriction existe déjà dans contest_types';
    END IF;
END $$;

-- Ajouter la colonne max_submissions_per_user si elle n'existe pas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest_types' AND column_name = 'max_submissions_per_user'
    ) THEN
        ALTER TABLE contest_types ADD COLUMN max_submissions_per_user INTEGER DEFAULT 1;
        RAISE NOTICE 'Colonne max_submissions_per_user ajoutée à contest_types';
    ELSE
        RAISE NOTICE 'Colonne max_submissions_per_user existe déjà dans contest_types';
    END IF;
END $$;

-- Ajouter la colonne upload_duration_days si elle n'existe pas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest_types' AND column_name = 'upload_duration_days'
    ) THEN
        ALTER TABLE contest_types ADD COLUMN upload_duration_days INTEGER DEFAULT 60;
        RAISE NOTICE 'Colonne upload_duration_days ajoutée à contest_types';
    ELSE
        RAISE NOTICE 'Colonne upload_duration_days existe déjà dans contest_types';
    END IF;
END $$;

-- Ajouter la colonne voting_duration_days si elle n'existe pas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest_types' AND column_name = 'voting_duration_days'
    ) THEN
        ALTER TABLE contest_types ADD COLUMN voting_duration_days INTEGER DEFAULT 60;
        RAISE NOTICE 'Colonne voting_duration_days ajoutée à contest_types';
    ELSE
        RAISE NOTICE 'Colonne voting_duration_days existe déjà dans contest_types';
    END IF;
END $$;

-- Ajouter la colonne is_active si elle n'existe pas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contest_types' AND column_name = 'is_active'
    ) THEN
        ALTER TABLE contest_types ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
        RAISE NOTICE 'Colonne is_active ajoutée à contest_types';
    ELSE
        RAISE NOTICE 'Colonne is_active existe déjà dans contest_types';
    END IF;
END $$;

-- Vérifier les colonnes de la table
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'contest_types' 
ORDER BY ordinal_position;

