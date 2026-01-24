-- Make date columns nullable in contest table
ALTER TABLE contest ALTER COLUMN submission_start_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN submission_end_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN voting_start_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN voting_end_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN city_season_start_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN city_season_end_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN country_season_start_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN country_season_end_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN regional_start_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN regional_end_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN continental_start_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN continental_end_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN global_start_date DROP NOT NULL;
ALTER TABLE contest ALTER COLUMN global_end_date DROP NOT NULL;
