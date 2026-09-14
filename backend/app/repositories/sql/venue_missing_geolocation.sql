-- Source contract: Uranus 7feb47e, ddl/venue.ddl, sql/get-event-dates.sql.
-- Each event_date contributes at most once. Space never supplies a missing venue.
WITH candidates AS (
    SELECT v.uuid, v.name, v.org_uuid, o.name AS organization_name,
           v.street, v.house_number, v.postal_code, v.city, v.country
    FROM uranus.venue v
    JOIN uranus.organization o ON o.uuid = v.org_uuid
    WHERE (v.point IS NULL OR ST_IsEmpty(v.point))
      AND (CAST(:organization_id AS uuid) IS NULL OR v.org_uuid = CAST(:organization_id AS uuid))
), upcoming AS (
    SELECT COALESCE(ed.venue_uuid, e.venue_uuid) AS venue_uuid,
           ed.start_date,
           e.release_status IN ('released', 'rescheduled')
           AND COALESCE(NULLIF(ed.release_status::text, 'inherited'), e.release_status::text)
               IN ('released', 'rescheduled') AS published
    FROM uranus.event_date ed
    JOIN uranus.event e ON e.uuid = ed.event_uuid
    JOIN candidates v ON v.uuid = COALESCE(ed.venue_uuid, e.venue_uuid)
    WHERE ed.start_date >= CAST(:local_date AS date)
      AND (ed.start_date > CAST(:local_date AS date)
           OR ed.all_day IS TRUE OR ed.start_time IS NULL
           OR ed.start_time >= CAST(:local_time AS time))
), counts AS (
    SELECT venue_uuid, COUNT(*) AS upcoming_event_date_count,
           COUNT(*) FILTER (WHERE published) AS upcoming_published_event_date_count,
           COUNT(*) FILTER (WHERE published AND start_date < CAST(:soon_end AS date))
               AS soon_published_event_date_count
    FROM upcoming
    GROUP BY venue_uuid
)
SELECT v.*,
       COALESCE(c.upcoming_event_date_count, 0) AS upcoming_event_date_count,
       COALESCE(c.upcoming_published_event_date_count, 0) AS upcoming_published_event_date_count,
       COALESCE(c.soon_published_event_date_count, 0) AS soon_published_event_date_count
FROM candidates v
LEFT JOIN counts c ON c.venue_uuid = v.uuid
