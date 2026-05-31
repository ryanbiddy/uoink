-- v3.2.3 default style anchors.
--
-- Flags rows seeded from defaults/style_anchors.json so the UI can tell the
-- curated defaults apart from user-added anchors. Defaults can be deactivated
-- but not deleted (they stay available to re-enable); user anchors behave as
-- before. Column is `is_default` (avoids the SQL reserved word `default`); the
-- API maps it to a `default` boolean. Existing rows are user-added, so the
-- DEFAULT 0 is correct for the backfill.
ALTER TABLE style_anchors ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_style_anchors_is_default
    ON style_anchors(is_default);
