-- Add media requirements columns to contest table
ALTER TABLE contest ADD COLUMN IF NOT EXISTS requires_video BOOLEAN DEFAULT false NOT NULL;
ALTER TABLE contest ADD COLUMN IF NOT EXISTS max_videos INTEGER DEFAULT 1 NOT NULL;
ALTER TABLE contest ADD COLUMN IF NOT EXISTS video_max_duration INTEGER DEFAULT 3000 NOT NULL;
ALTER TABLE contest ADD COLUMN IF NOT EXISTS video_max_size_mb INTEGER DEFAULT 500 NOT NULL;
ALTER TABLE contest ADD COLUMN IF NOT EXISTS min_images INTEGER DEFAULT 0 NOT NULL;
ALTER TABLE contest ADD COLUMN IF NOT EXISTS max_images INTEGER DEFAULT 10 NOT NULL;
ALTER TABLE contest ADD COLUMN IF NOT EXISTS verification_video_max_duration INTEGER DEFAULT 30 NOT NULL;
ALTER TABLE contest ADD COLUMN IF NOT EXISTS verification_max_size_mb INTEGER DEFAULT 50 NOT NULL;

-- Create contestant_verifications table
CREATE TABLE IF NOT EXISTS contestant_verifications (
    id SERIAL PRIMARY KEY,
    contestant_id INTEGER NOT NULL REFERENCES contestants(id),
    verification_type VARCHAR(50) NOT NULL,
    media_url VARCHAR(500) NOT NULL,
    media_type VARCHAR(20) NOT NULL,
    duration_seconds INTEGER,
    file_size_bytes INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    rejection_reason TEXT,
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_contestant_verifications_contestant_id ON contestant_verifications(contestant_id);
CREATE INDEX IF NOT EXISTS ix_contestant_verifications_status ON contestant_verifications(status);
