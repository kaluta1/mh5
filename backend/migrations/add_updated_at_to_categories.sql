-- Migration: Add updated_at column to categories table if it doesn't exist
-- This column is required by the Base model

-- Add updated_at column if it doesn't exist
ALTER TABLE categories 
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;

-- Update existing rows to set updated_at = created_at if updated_at is NULL
UPDATE categories 
SET updated_at = created_at 
WHERE updated_at IS NULL;

-- Create a trigger to automatically update updated_at on row update
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Drop trigger if it exists and create it
DROP TRIGGER IF EXISTS update_categories_updated_at ON categories;
CREATE TRIGGER update_categories_updated_at
    BEFORE UPDATE ON categories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

