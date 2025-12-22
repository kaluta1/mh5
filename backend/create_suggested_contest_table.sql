-- Créer le type ENUM pour le statut si il n'existe pas
DO $$ BEGIN
    CREATE TYPE suggestedconteststatus AS ENUM ('pending', 'approved', 'rejected');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Créer la table suggested_contest si elle n'existe pas
CREATE TABLE IF NOT EXISTS suggested_contest (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100) NOT NULL,
    status suggestedconteststatus NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

