-- Script pour corriger les clés étrangères qui pointent vers "user" au lieu de "users"
-- À exécuter sur Render

-- Corriger la clé étrangère de la table comment
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'comment_user_id_fkey' AND table_name = 'comment'
    ) THEN
        ALTER TABLE comment DROP CONSTRAINT comment_user_id_fkey;
        RAISE NOTICE 'Contrainte comment_user_id_fkey supprimée';
    END IF;
    
    ALTER TABLE comment ADD CONSTRAINT comment_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);
    RAISE NOTICE 'Contrainte comment_user_id_fkey recréée avec users';
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Erreur comment: %', SQLERRM;
END $$;

-- Table like
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'like_user_id_fkey' AND table_name = 'like'
    ) THEN
        ALTER TABLE "like" DROP CONSTRAINT like_user_id_fkey;
        RAISE NOTICE 'Contrainte like_user_id_fkey supprimée';
    END IF;
    
    ALTER TABLE "like" ADD CONSTRAINT like_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);
    RAISE NOTICE 'Contrainte like_user_id_fkey recréée avec users';
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Erreur like: %', SQLERRM;
END $$;

-- Table my_favorites
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'my_favorites_user_id_fkey' AND table_name = 'my_favorites'
    ) THEN
        ALTER TABLE my_favorites DROP CONSTRAINT my_favorites_user_id_fkey;
    END IF;
    
    ALTER TABLE my_favorites ADD CONSTRAINT my_favorites_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);
    RAISE NOTICE 'Contrainte my_favorites_user_id_fkey corrigée';
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
    END IF;
    
    ALTER TABLE report ADD CONSTRAINT report_reporter_id_fkey 
        FOREIGN KEY (reporter_id) REFERENCES users(id);
    RAISE NOTICE 'Contrainte report_reporter_id_fkey corrigée';
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Erreur report: %', SQLERRM;
END $$;

-- Table media
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'media_user_id_fkey' AND table_name = 'media'
    ) THEN
        ALTER TABLE media DROP CONSTRAINT media_user_id_fkey;
    END IF;
    
    ALTER TABLE media ADD CONSTRAINT media_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);
    RAISE NOTICE 'Contrainte media_user_id_fkey corrigée';
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Erreur media: %', SQLERRM;
END $$;

-- Table contest_entry
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'contest_entry_user_id_fkey' AND table_name = 'contest_entry'
    ) THEN
        ALTER TABLE contest_entry DROP CONSTRAINT contest_entry_user_id_fkey;
    END IF;
    
    ALTER TABLE contest_entry ADD CONSTRAINT contest_entry_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);
    RAISE NOTICE 'Contrainte contest_entry_user_id_fkey corrigée';
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Erreur contest_entry: %', SQLERRM;
END $$;

-- Table contest_vote
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'contest_vote_user_id_fkey' AND table_name = 'contest_vote'
    ) THEN
        ALTER TABLE contest_vote DROP CONSTRAINT contest_vote_user_id_fkey;
    END IF;
    
    ALTER TABLE contest_vote ADD CONSTRAINT contest_vote_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);
    RAISE NOTICE 'Contrainte contest_vote_user_id_fkey corrigée';
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'Erreur contest_vote: %', SQLERRM;
END $$;

-- Afficher toutes les clés étrangères qui référencent encore "user" (singulier)
SELECT 
    tc.table_name, 
    tc.constraint_name,
    ccu.table_name AS foreign_table_name
FROM information_schema.table_constraints tc
JOIN information_schema.constraint_column_usage ccu 
    ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
    AND ccu.table_name = 'user';

