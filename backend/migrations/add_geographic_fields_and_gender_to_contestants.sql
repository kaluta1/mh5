-- Migration: Add geographic fields (city, country, region, continent) and author_gender to contestants table
-- Date: 2024-12-XX
-- Description: Ajoute les champs géographiques et le genre de l'auteur à la table contestants

-- Vérifier si les colonnes existent avant de les ajouter
DO $$ 
BEGIN
    -- Ajouter la colonne city si elle n'existe pas
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contestants' AND column_name = 'city'
    ) THEN
        ALTER TABLE contestants ADD COLUMN city VARCHAR(100);
    END IF;

    -- Ajouter la colonne country si elle n'existe pas
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contestants' AND column_name = 'country'
    ) THEN
        ALTER TABLE contestants ADD COLUMN country VARCHAR(100);
    END IF;

    -- Ajouter la colonne region si elle n'existe pas
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contestants' AND column_name = 'region'
    ) THEN
        ALTER TABLE contestants ADD COLUMN region VARCHAR(100);
    END IF;

    -- Ajouter la colonne continent si elle n'existe pas
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contestants' AND column_name = 'continent'
    ) THEN
        ALTER TABLE contestants ADD COLUMN continent VARCHAR(100);
    END IF;

    -- Ajouter la colonne author_gender si elle n'existe pas
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contestants' AND column_name = 'author_gender'
    ) THEN
        ALTER TABLE contestants ADD COLUMN author_gender VARCHAR(50);
    END IF;
END $$;

-- Optionnel: Mettre à jour les données existantes en copiant depuis la table users
-- Cette requête met à jour les contestants existants avec les données de leur utilisateur
UPDATE contestants c
SET 
    city = u.city,
    country = u.country,
    region = u.region,
    continent = u.continent,
    author_gender = CASE 
        WHEN u.gender IS NOT NULL THEN 
            CASE u.gender::text
                WHEN 'MALE' THEN 'male'
                WHEN 'FEMALE' THEN 'female'
                WHEN 'OTHER' THEN 'other'
                WHEN 'PREFER_NOT_TO_SAY' THEN 'prefer_not_to_say'
                ELSE u.gender::text
            END
        ELSE NULL
    END
FROM users u
WHERE c.user_id = u.id
  AND (c.city IS NULL OR c.country IS NULL OR c.region IS NULL OR c.continent IS NULL OR c.author_gender IS NULL);

-- Commentaire sur les colonnes
COMMENT ON COLUMN contestants.city IS 'Ville de l''auteur (copiée depuis users.city lors de la création)';
COMMENT ON COLUMN contestants.country IS 'Pays de l''auteur (copié depuis users.country lors de la création)';
COMMENT ON COLUMN contestants.region IS 'Région de l''auteur (copiée depuis users.region lors de la création)';
COMMENT ON COLUMN contestants.continent IS 'Continent de l''auteur (copié depuis users.continent lors de la création)';
COMMENT ON COLUMN contestants.author_gender IS 'Genre de l''auteur (copié depuis users.gender lors de la création)';
