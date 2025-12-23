-- Script SQL pour ajouter les colonnes contestant_id et contest_id à la table report
-- À exécuter si la migration Alembic ne fonctionne pas

-- Vérifier et ajouter la colonne contestant_id
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'report' 
        AND column_name = 'contestant_id'
    ) THEN
        ALTER TABLE report 
        ADD COLUMN contestant_id INTEGER;
        
        -- Ajouter la contrainte de clé étrangère
        ALTER TABLE report
        ADD CONSTRAINT fk_report_contestant_id
        FOREIGN KEY (contestant_id) 
        REFERENCES contestants(id) 
        ON DELETE CASCADE;
    END IF;
END $$;

-- Vérifier et ajouter la colonne contest_id
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'report' 
        AND column_name = 'contest_id'
    ) THEN
        ALTER TABLE report 
        ADD COLUMN contest_id INTEGER;
        
        -- Ajouter la contrainte de clé étrangère
        ALTER TABLE report
        ADD CONSTRAINT fk_report_contest_id
        FOREIGN KEY (contest_id) 
        REFERENCES contest(id) 
        ON DELETE CASCADE;
    END IF;
END $$;

