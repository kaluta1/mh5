-- Migration: Create categories table and add category_id to contest table
-- A contest has one category, a category can be in multiple contests

-- Create categories table if it doesn't exist
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Add updated_at column if table exists but column doesn't (for existing tables)
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'categories') 
       AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'categories' AND column_name = 'updated_at') THEN
        ALTER TABLE categories ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL;
        UPDATE categories SET updated_at = created_at WHERE updated_at IS NULL;
    END IF;
END $$;

-- Create index on slug for faster lookups
CREATE INDEX IF NOT EXISTS idx_categories_slug ON categories(slug);
CREATE INDEX IF NOT EXISTS idx_categories_is_active ON categories(is_active);

-- Add category_id column to contest table if it doesn't exist
ALTER TABLE contest 
ADD COLUMN IF NOT EXISTS category_id INTEGER;

-- Add foreign key constraint if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'contest_category_id_fkey'
    ) THEN
        ALTER TABLE contest 
        ADD CONSTRAINT contest_category_id_fkey 
        FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Create index on category_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_contest_category_id ON contest(category_id);

