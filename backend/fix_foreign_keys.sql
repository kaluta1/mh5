-- Script pour corriger les clés étrangères qui pointent vers "user" au lieu de "users"
-- À exécuter sur Render

-- Corriger la clé étrangère de la table comment
DO $$
BEGIN
    -- Supprimer l'ancienne contrainte si elle existe
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'comment_user_id_fkey' AND table_name = 'comment'
    ) THEN
        ALTER TABLE comment DROP CONSTRAINT comment_user_id_fkey;
        RAISE NOTICE 'Contrainte comment_user_id_fkey supprimée';
    END IF;
    
    -- Recréer la contrainte avec la bonne table
    ALTER TABLE comment ADD CONSTRAINT comment_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);
    RAISE NOTICE 'Contrainte comment_user_id_fkey recréée avec users';
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Erreur lors de la correction de comment_user_id_fkey: %', SQLERRM;
END $$;

-- Corriger les autres tables qui pourraient avoir le même problème

-- Table my_favorites
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'my_favorites_user_id_fkey' AND table_name = 'my_favorites'
    ) THEN
        -- Vérifier si elle pointe vers 'user' au lieu de 'users'
        ALTER TABLE my_favorites DROP CONSTRAINT my_favorites_user_id_fkey;
        ALTER TABLE my_favorites ADD CONSTRAINT my_favorites_user_id_fkey 
            FOREIGN KEY (user_id) REFERENCES users(id);
        RAISE NOTICE 'Contrainte my_favorites_user_id_fkey corrigée';
    END IF;
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Erreur my_favorites: %', SQLERRM;
END $$;

-- Table report
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'report_reporter_id_fkey' AND table_name = 'report'
    ) THEN
        ALTER TABLE report DROP CONSTRAINT report_reporter_id_fkey;
        ALTER TABLE report ADD CONSTRAINT report_reporter_id_fkey 
            FOREIGN KEY (reporter_id) REFERENCES users(id);
        RAISE NOTICE 'Contrainte report_reporter_id_fkey corrigée';
    END IF;
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Erreur report: %', SQLERRM;
END $$;

-- Afficher toutes les clés étrangères qui référencent "user" (singulier)
SELECT 
    tc.table_name, 
    tc.constraint_name,
    ccu.table_name AS foreign_table_name
FROM information_schema.table_constraints tc
JOIN information_schema.constraint_column_usage ccu 
    ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
    AND ccu.table_name = 'user';

