-- Script pour corriger la table my_favorites sur Render
-- La colonne contest_type_id n'est pas utilisée dans le modèle mais existe dans la table

-- Option 1: Supprimer la contrainte NOT NULL sur contest_type_id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'my_favorites' AND column_name = 'contest_type_id'
    ) THEN
        ALTER TABLE my_favorites ALTER COLUMN contest_type_id DROP NOT NULL;
        RAISE NOTICE 'Contrainte NOT NULL supprimée de contest_type_id';
    ELSE
        RAISE NOTICE 'Colonne contest_type_id n existe pas dans my_favorites';
    END IF;
END $$;

-- Option 2 (alternative): Supprimer complètement la colonne si non utilisée
-- Décommentez les lignes suivantes si vous voulez supprimer la colonne
-- DO $$
-- BEGIN
--     IF EXISTS (
--         SELECT 1 FROM information_schema.columns 
--         WHERE table_name = 'my_favorites' AND column_name = 'contest_type_id'
--     ) THEN
--         ALTER TABLE my_favorites DROP COLUMN contest_type_id;
--         RAISE NOTICE 'Colonne contest_type_id supprimée de my_favorites';
--     END IF;
-- END $$;

-- Vérifier la structure de la table
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'my_favorites' 
ORDER BY ordinal_position;

