-- Migration des contestants existants pour les lier aux rounds
-- Version corrigée : Utilise season_id au lie de contest_id

DO $$
DECLARE
    contestant_record RECORD;
    round_record RECORD;
    migrated_count INTEGER := 0;
BEGIN
    -- Parcourir tous les contestants qui n'ont pas de round_id 
    -- On utilise season_id car contest_id n'existe pas dans la table contestants
    FOR contestant_record IN 
        SELECT id, season_id, created_at 
        FROM contestants 
        WHERE round_id IS NULL AND season_id IS NOT NULL 
    LOOP
        -- Trouver un round approprié pour ce contest (via season_id qui agit comme contest_id)
        -- 1. Chercher un round actif
        SELECT r.id INTO round_record
        FROM rounds r
        JOIN round_contests rc ON rc.round_id = r.id
        WHERE rc.contest_id = contestant_record.season_id
        AND r.status = 'active'
        LIMIT 1;
        
        -- 2. Si pas de round actif, chercher n'importe quel round lié
        IF round_record.id IS NULL THEN
            SELECT r.id INTO round_record
            FROM rounds r
            JOIN round_contests rc ON rc.round_id = r.id
            WHERE rc.contest_id = contestant_record.season_id
            ORDER BY r.created_at DESC
            LIMIT 1;
        END IF;
        
        -- Si un round est trouvé, mettre à jour le contestant
        IF round_record.id IS NOT NULL THEN
            UPDATE contestants
            SET round_id = round_record.id
            WHERE id = contestant_record.id;
            
            migrated_count := migrated_count + 1;
        END IF;
    END LOOP;
    
    RAISE NOTICE 'Migration terminée : % contestants mis à jour.', migrated_count;
END $$;
