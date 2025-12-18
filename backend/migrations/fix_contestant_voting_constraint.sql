-- Script SQL pour modifier la contrainte unique sur contestant_voting
-- De (user_id, contestant_id, contest_id) vers (user_id, contestant_id, season_id)
-- Un utilisateur peut voter pour plusieurs contestants dans la même saison,
-- mais ne peut pas voter deux fois pour le même contestant dans la même saison

-- Étape 1: Nettoyer les doublons (garder le vote le plus récent par utilisateur/contestant/saison)
DELETE FROM contestant_voting
WHERE id NOT IN (
    SELECT DISTINCT ON (user_id, contestant_id, season_id) id
    FROM contestant_voting
    ORDER BY user_id, contestant_id, season_id, vote_date DESC, id DESC
);

-- Étape 2: Supprimer l'ancienne contrainte unique
ALTER TABLE contestant_voting 
DROP CONSTRAINT IF EXISTS uq_contestant_voting;

-- Étape 3: Créer la nouvelle contrainte unique sur (user_id, contestant_id, season_id)
ALTER TABLE contestant_voting 
ADD CONSTRAINT uq_contestant_voting 
UNIQUE (user_id, contestant_id, season_id);

