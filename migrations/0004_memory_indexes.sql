-- Uoink library index -- soft-delete support (v4, Sprint 18 / B1).
-- Applied by index._run_migrations() on top of 0003. Adds the deleted_at
-- column that drives soft delete to the _yoink-trash/ folder and the
-- 30-day scheduled purge.
--
-- The Sprint 18 brief proposed compound (yoinked_at DESC, <filter>) indexes
-- for the memory page's filtered queries, gated on EXPLAIN QUERY PLAN
-- showing a full scan. EXPLAIN was run on every filter combination
-- (channel / topic / hook_type / date range, alone and combined): none
-- produces a full table scan -- each is already served by a single-column
-- index, and the proposed compound indexes are not picked by the planner
-- at all (a leading DESC sort column cannot seed an equality seek on the
-- second column). They are therefore omitted; only deleted_at is added.

ALTER TABLE yoinks ADD COLUMN deleted_at TEXT;
CREATE INDEX IF NOT EXISTS idx_yoinks_deleted_at ON yoinks(deleted_at);
