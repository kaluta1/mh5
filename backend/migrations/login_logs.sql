-- Script SQL pour créer la table login_logs
-- Compatible PostgreSQL

-- Créer la table login_logs
CREATE TABLE IF NOT EXISTS login_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    device_info JSONB,
    location_info JSONB,
    login_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_successful BOOLEAN NOT NULL DEFAULT TRUE,
    failure_reason VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_login_logs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Créer les index pour améliorer les performances
CREATE INDEX IF NOT EXISTS ix_login_logs_user_id ON login_logs(user_id);
CREATE INDEX IF NOT EXISTS ix_login_logs_ip_address ON login_logs(ip_address);
CREATE INDEX IF NOT EXISTS ix_login_logs_login_at ON login_logs(login_at);
CREATE INDEX IF NOT EXISTS ix_login_logs_is_successful ON login_logs(is_successful);

-- Créer un index composite pour les requêtes fréquentes (user_id + login_at)
CREATE INDEX IF NOT EXISTS ix_login_logs_user_login_at ON login_logs(user_id, login_at DESC);

-- Créer une fonction trigger pour mettre à jour automatiquement updated_at
CREATE OR REPLACE FUNCTION update_login_logs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Créer le trigger pour mettre à jour updated_at automatiquement
CREATE TRIGGER update_login_logs_updated_at
    BEFORE UPDATE ON login_logs
    FOR EACH ROW
    EXECUTE FUNCTION update_login_logs_updated_at();

-- Commentaires pour la documentation
COMMENT ON TABLE login_logs IS 'Table pour stocker les logs de connexion des utilisateurs';
COMMENT ON COLUMN login_logs.user_id IS 'ID de l''utilisateur qui s''est connecté';
COMMENT ON COLUMN login_logs.ip_address IS 'Adresse IP de la connexion (IPv4 ou IPv6)';
COMMENT ON COLUMN login_logs.user_agent IS 'User-Agent du navigateur/appareil';
COMMENT ON COLUMN login_logs.device_info IS 'Informations de l''appareil (platform, browser, screen_size, etc.) au format JSON';
COMMENT ON COLUMN login_logs.location_info IS 'Informations de localisation (country, city, continent, timezone, etc.) au format JSON';
COMMENT ON COLUMN login_logs.login_at IS 'Date et heure de la connexion';
COMMENT ON COLUMN login_logs.is_successful IS 'Indique si la connexion a réussi';
COMMENT ON COLUMN login_logs.failure_reason IS 'Raison de l''échec si is_successful = FALSE';

