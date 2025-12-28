-- Script pour corriger la table my_favorites sur Render
-- Plusieurs colonnes ne sont pas utilisées dans le modèle mais existent dans la table avec NOT NULL

-- Supprimer la contrainte NOT NULL sur contest_type_id
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

-- Supprimer la contrainte NOT NULL sur stage_id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'my_favorites' AND column_name = 'stage_id'
    ) THEN
        ALTER TABLE my_favorites ALTER COLUMN stage_id DROP NOT NULL;
        RAISE NOTICE 'Contrainte NOT NULL supprimée de stage_id';
    ELSE
        RAISE NOTICE 'Colonne stage_id n existe pas dans my_favorites';
    END IF;
END $$;

-- Supprimer la contrainte NOT NULL sur contest_id (si existe)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'my_favorites' AND column_name = 'contest_id'
    ) THEN
        ALTER TABLE my_favorites ALTER COLUMN contest_id DROP NOT NULL;
        RAISE NOTICE 'Contrainte NOT NULL supprimée de contest_id';
    ELSE
        RAISE NOTICE 'Colonne contest_id n existe pas dans my_favorites';
    END IF;
END $$;

-- Supprimer la contrainte NOT NULL sur season_id (si existe)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'my_favorites' AND column_name = 'season_id'
    ) THEN
        ALTER TABLE my_favorites ALTER COLUMN season_id DROP NOT NULL;
        RAISE NOTICE 'Contrainte NOT NULL supprimée de season_id';
    ELSE
        RAISE NOTICE 'Colonne season_id n existe pas dans my_favorites';
    END IF;
END $$;

-- Vérifier la structure de la table
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'my_favorites' 
ORDER BY ordinal_position;

