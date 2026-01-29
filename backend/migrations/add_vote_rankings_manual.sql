-- Ajout de la table user_vote_rankings pour le système de vote par classement (5 votes max par round)

CREATE TABLE IF NOT EXISTS user_vote_rankings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    round_id INTEGER NOT NULL,
    contestant_id INTEGER NOT NULL,
    position INTEGER NOT NULL, -- 1-5
    points INTEGER NOT NULL,   -- 5,4,3,2,1
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Contraintes de clés étrangères
    CONSTRAINT fk_vote_rankings_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_vote_rankings_round FOREIGN KEY (round_id) REFERENCES rounds(id) ON DELETE CASCADE,
    CONSTRAINT fk_vote_rankings_contestant FOREIGN KEY (contestant_id) REFERENCES contestants(id) ON DELETE CASCADE,
    
    -- Contrainte unique : un utilisateur ne peut voter qu'une fois pour un contestant dans un round
    CONSTRAINT unique_user_round_contestant_vote UNIQUE (user_id, round_id, contestant_id)
);

-- Création des index pour les performances
CREATE INDEX IF NOT EXISTS idx_vote_rankings_user_round ON user_vote_rankings(user_id, round_id);
CREATE INDEX IF NOT EXISTS idx_vote_rankings_contestant ON user_vote_rankings(contestant_id);
CREATE INDEX IF NOT EXISTS idx_vote_rankings_round ON user_vote_rankings(round_id);

-- Ajout de la colonne round_id à la table contest_votes si elle n'existe pas déjà
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'contest_votes' AND column_name = 'round_id') THEN
        ALTER TABLE contest_votes ADD COLUMN round_id INTEGER;
        ALTER TABLE contest_votes ADD CONSTRAINT fk_contest_votes_round FOREIGN KEY (round_id) REFERENCES rounds(id);
    END IF;
END
$$;
