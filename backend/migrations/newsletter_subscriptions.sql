-- Script SQL pour créer la table newsletter_subscriptions
-- Compatible PostgreSQL

-- Créer la table newsletter_subscriptions
CREATE TABLE IF NOT EXISTS newsletter_subscriptions (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    device_info JSONB,
    location_info JSONB,
    verified_at TIMESTAMP,
    unsubscribed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Créer un index sur l'email pour améliorer les performances de recherche
CREATE INDEX IF NOT EXISTS ix_newsletter_subscriptions_email ON newsletter_subscriptions(email);

-- Créer un index sur is_active pour filtrer rapidement les abonnements actifs
CREATE INDEX IF NOT EXISTS ix_newsletter_subscriptions_is_active ON newsletter_subscriptions(is_active);

-- Créer un index sur created_at pour trier par date de création
CREATE INDEX IF NOT EXISTS ix_newsletter_subscriptions_created_at ON newsletter_subscriptions(created_at);

-- Créer une fonction trigger pour mettre à jour automatiquement updated_at
CREATE OR REPLACE FUNCTION update_newsletter_subscriptions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Créer le trigger pour mettre à jour updated_at automatiquement
CREATE TRIGGER update_newsletter_subscriptions_updated_at
    BEFORE UPDATE ON newsletter_subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_newsletter_subscriptions_updated_at();

-- Commentaires pour la documentation
COMMENT ON TABLE newsletter_subscriptions IS 'Table pour stocker les abonnements à la newsletter';
COMMENT ON COLUMN newsletter_subscriptions.email IS 'Adresse email de l''abonné (unique)';
COMMENT ON COLUMN newsletter_subscriptions.is_active IS 'Indique si l''abonnement est actif';
COMMENT ON COLUMN newsletter_subscriptions.is_verified IS 'Indique si l''email a été vérifié';
COMMENT ON COLUMN newsletter_subscriptions.device_info IS 'Informations de l''appareil (user_agent, platform, browser, etc.) au format JSON';
COMMENT ON COLUMN newsletter_subscriptions.location_info IS 'Informations de localisation (country, city, continent, ip, timezone, etc.) au format JSON';
COMMENT ON COLUMN newsletter_subscriptions.verified_at IS 'Date de vérification de l''email';
COMMENT ON COLUMN newsletter_subscriptions.unsubscribed_at IS 'Date de désinscription de la newsletter';

