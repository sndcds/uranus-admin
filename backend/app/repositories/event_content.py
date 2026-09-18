"""One bounded aggregate result; fixed source identifiers and no domain hydration."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.repositories.spatial import spatial_predicate
from app.services.periods import PeriodWindow

# Source: sndcds/uranus 0c2632e, ddl/{event,event_category,event_type,event_type_link,genre_type}.
# AdminUpdateEventTypes explicitly writes 0 when genre_id is omitted.
CONTENT_SQL = """
WITH windows AS (
    SELECT * FROM unnest(CAST(:starts AS timestamptz[]), CAST(:ends AS timestamptz[]))
    WITH ORDINALITY AS w(start_at,end_at,window_id)
), filtered_events AS MATERIALIZED (
    SELECT w.window_id,e.uuid,e.categories FROM uranus.event e JOIN windows w
    ON (w.start_at IS NULL OR (e.created_at AT TIME ZONE :tz >= w.start_at
        AND e.created_at AT TIME ZONE :tz < w.end_at))
    WHERE (CAST(:status AS text) IS NULL OR e.release_status::text=:status)
), assignments AS MATERIALIZED (
    SELECT f.window_id,f.uuid,'categories' dimension,c.id::text id,c.id numeric_id,
        NULL::integer type_id FROM filtered_events f
    CROSS JOIN LATERAL unnest(f.categories) c(id) WHERE c.id IS NOT NULL
    UNION
    SELECT f.window_id,f.uuid,'event_types',l.type_id::text,l.type_id,l.type_id
    FROM filtered_events f JOIN uranus.event_type_link l ON l.event_uuid=f.uuid
    UNION
    SELECT f.window_id,f.uuid,'genres',l.type_id::text||':'||l.genre_id::text,l.genre_id,l.type_id
    FROM filtered_events f JOIN uranus.event_type_link l ON l.event_uuid=f.uuid
    WHERE l.genre_id<>0
), category_labels AS (
    SELECT DISTINCT ON (category_id) category_id,name FROM uranus.event_category
    WHERE NULLIF(trim(name),'') IS NOT NULL
    ORDER BY category_id,CASE iso_639_1 WHEN 'de' THEN 0 WHEN 'en' THEN 1 ELSE 2 END,
        iso_639_1 COLLATE "C" NULLS LAST,name COLLATE "C"
), type_labels AS (
    SELECT DISTINCT ON (type_id) type_id,name FROM uranus.event_type
    WHERE NULLIF(trim(name),'') IS NOT NULL
    ORDER BY type_id,CASE iso_639_1 WHEN 'de' THEN 0 WHEN 'en' THEN 1 ELSE 2 END,
        iso_639_1 COLLATE "C" NULLS LAST,name COLLATE "C"
), genre_labels AS (
    SELECT DISTINCT ON (type_id,genre_id) type_id,genre_id,name FROM uranus.genre_type
    WHERE NULLIF(trim(name),'') IS NOT NULL
    ORDER BY type_id,genre_id,CASE iso_639_1 WHEN 'de' THEN 0 WHEN 'en' THEN 1 ELSE 2 END,
        iso_639_1 COLLATE "C" NULLS LAST,name COLLATE "C"
), counts AS (
    SELECT window_id,dimension,id,numeric_id,type_id,count(DISTINCT uuid) event_count
    FROM assignments GROUP BY window_id,dimension,id,numeric_id,type_id
), named AS (
    SELECT a.*,CASE dimension
        WHEN 'categories' THEN COALESCE(c.name,'Kategorie '||a.id)
        WHEN 'event_types' THEN COALESCE(t.name,'Event-Typ '||a.id)
        ELSE COALESCE(t.name,'Event-Typ '||a.type_id)||' · '||
            COALESCE(g.name,'Genre '||a.numeric_id) END name
    FROM counts a
    LEFT JOIN category_labels c ON a.dimension='categories' AND c.category_id=a.numeric_id
    LEFT JOIN type_labels t ON t.type_id=a.type_id
    LEFT JOIN genre_labels g ON a.dimension='genres'
        AND g.type_id=a.type_id AND g.genre_id=a.numeric_id
), ranked AS (
    SELECT *,row_number() OVER (PARTITION BY window_id,dimension
        ORDER BY event_count DESC,name COLLATE "C",id COLLATE "C") rank FROM named
), totals AS (
    SELECT w.window_id,count(f.uuid) event_count FROM windows w
    LEFT JOIN filtered_events f USING (window_id) GROUP BY w.window_id
), summaries AS (
    SELECT t.window_id,d.dimension,t.event_count,count(DISTINCT a.uuid) with_assignment,
        count(DISTINCT a.id) distinct_assignments
    FROM totals t CROSS JOIN (VALUES ('categories'),('genres'),('event_types')) d(dimension)
    LEFT JOIN assignments a ON a.window_id=t.window_id AND a.dimension=d.dimension
    GROUP BY t.window_id,d.dimension,t.event_count
)
SELECT s.*,r.id,r.name,r.rank,r.event_count assigned_count,
    p.rank previous_rank,COALESCE(p.event_count,0) previous_assigned_count,
    old.event_count previous_total,old.with_assignment previous_with_assignment
FROM summaries s LEFT JOIN ranked r
    ON r.window_id=s.window_id AND r.dimension=s.dimension AND r.rank<=10
LEFT JOIN ranked p ON p.window_id=2 AND p.dimension=r.dimension AND p.id=r.id
LEFT JOIN summaries old ON old.window_id=2 AND old.dimension=s.dimension
WHERE s.window_id=1 ORDER BY s.dimension,r.rank
"""


async def aggregate_event_content(
    connection: AsyncConnection,
    window: PeriodWindow | None,
    previous: PeriodWindow | None,
    timezone: str,
    status: str | None,
    geo_scope_wkb: bytes | None = None,
) -> list[dict[str, Any]]:
    windows = [window, previous] if previous else [window]
    sql = CONTENT_SQL
    if geo_scope_wkb is not None:
        sql = sql.replace(
            "), assignments AS",
            " AND " + spatial_predicate("event", key_expression="e.uuid") + "), assignments AS",
        )
    result = await connection.execute(
        text(sql),
        {
            "geo_scope_wkb": geo_scope_wkb,
            "starts": [w.start if w else None for w in windows],
            "ends": [w.end if w else None for w in windows],
            "tz": timezone,
            "status": status,
        },
    )
    return [dict(row) for row in result.mappings()]
