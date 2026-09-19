-- Run this whole file at once: psql -U your_user -d your_dbname -f postgres_monitoring.sql
-- Do it WHILE Locust is running to see live load stats.

\echo '--- 1. Active Connections ---'
SELECT count(*) AS active_connections
FROM pg_stat_activity
WHERE state = 'active';

\echo '--- 2. Currently Running Queries ---'
SELECT pid, now() - query_start AS duration, state, query
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC;

\echo '--- 3. Busiest Tables ---'
SELECT relname, seq_scan, idx_scan, n_tup_ins, n_tup_upd, n_tup_del
FROM pg_stat_user_tables
ORDER BY seq_scan DESC;

\echo '--- 4. Cache Hit Ratio (want close to 1.0) ---'
SELECT
  sum(heap_blks_hit) / nullif(sum(heap_blks_hit) + sum(heap_blks_read), 0) AS cache_hit_ratio
FROM pg_statio_user_tables;
