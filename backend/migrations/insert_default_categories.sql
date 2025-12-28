-- Script to insert default categories
-- These categories will be used for contests

INSERT INTO categories (name, slug, description, is_active, created_at)
VALUES 
    ('Pop', 'pop', 'Pop music category', TRUE, CURRENT_TIMESTAMP),
    ('Rock', 'rock', 'Rock music category', TRUE, CURRENT_TIMESTAMP),
    ('Hip hop', 'hip-hop', 'Hip hop music category', TRUE, CURRENT_TIMESTAMP),
    ('Electronic dance music (EDM)', 'edm', 'Electronic dance music category', TRUE, CURRENT_TIMESTAMP),
    ('R and B', 'r-and-b', 'R&B music category', TRUE, CURRENT_TIMESTAMP),
    ('Jazz', 'jazz', 'Jazz music category', TRUE, CURRENT_TIMESTAMP),
    ('Classical', 'classical', 'Classical music category', TRUE, CURRENT_TIMESTAMP),
    ('Reggae', 'reggae', 'Reggae music category', TRUE, CURRENT_TIMESTAMP),
    ('Country', 'country', 'Country music category', TRUE, CURRENT_TIMESTAMP),
    ('Afrobeat', 'afrobeat', 'Afrobeat music category', TRUE, CURRENT_TIMESTAMP)
ON CONFLICT (name) DO NOTHING;

-- Verify the insertions
SELECT id, name, slug, is_active FROM categories ORDER BY name;

