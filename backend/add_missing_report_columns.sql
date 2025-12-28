-- Script pour ajouter les colonnes manquantes à la table report
-- À exécuter sur Render via la console SQL de PostgreSQL

-- Ajouter la colonne contestant_id si elle n'existe pas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'report' AND column_name = 'contestant_id'
    ) THEN
        ALTER TABLE report ADD COLUMN contestant_id INTEGER REFERENCES contestants(id);
        RAISE NOTICE 'Colonne contestant_id ajoutée à report';
    ELSE
        RAISE NOTICE 'Colonne contestant_id existe déjà dans report';
    END IF;
END $$;

-- Ajouter la colonne contest_id si elle n'existe pas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'report' AND column_name = 'contest_id'
    ) THEN
        ALTER TABLE report ADD COLUMN contest_id INTEGER REFERENCES contest(id);
        RAISE NOTICE 'Colonne contest_id ajoutée à report';
    ELSE
        RAISE NOTICE 'Colonne contest_id existe déjà dans report';
    END IF;
END $$;

-- Ajouter la colonne contest_entry_id si elle n'existe pas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'report' AND column_name = 'contest_entry_id'
    ) THEN
        ALTER TABLE report ADD COLUMN contest_entry_id INTEGER REFERENCES contest_entry(id);
        RAISE NOTICE 'Colonne contest_entry_id ajoutée à report';
    ELSE
        RAISE NOTICE 'Colonne contest_entry_id existe déjà dans report';
    END IF;
END $$;

-- Vérifier les colonnes de la table
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'report' 
ORDER BY ordinal_position;

