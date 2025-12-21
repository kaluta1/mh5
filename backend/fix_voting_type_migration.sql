-- Script SQL pour ajouter manuellement la colonne voting_type_id si la migration a échoué
-- À exécuter directement dans PostgreSQL si nécessaire

-- Vérifier si la colonne existe déjà
DO $$
BEGIN
    -- Ajouter la colonne voting_type_id si elle n'existe pas
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'contest' 
        AND column_name = 'voting_type_id'
    ) THEN
        ALTER TABLE contest ADD COLUMN voting_type_id INTEGER;
        
        -- Créer la clé étrangère si la table voting_type existe
        IF EXISTS (
            SELECT 1 
            FROM information_schema.tables 
            WHERE table_name = 'voting_type'
        ) THEN
            ALTER TABLE contest 
            ADD CONSTRAINT fk_contest_voting_type 
            FOREIGN KEY (voting_type_id) 
            REFERENCES voting_type(id) 
            ON DELETE SET NULL;
        END IF;
    END IF;
END $$;

