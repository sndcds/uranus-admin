"""Shared authoritative public taxonomy projections, including localized labels."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.repositories.research import GENRE_LABELS
from app.repositories.vector_events import PUBLIC_EVENT
from app.research.taxonomy import LocalizedLabel, TaxonomyRow

# Canonical labels and public event eligibility shared with semantic indexing.
GENRES_SQL = f"""WITH genres AS ({GENRE_LABELS})
    SELECT g.type_id::text || ':' || g.genre_id::text id,g.name label,g.name name
    FROM genres g WHERE g.genre_id<>0
    AND EXISTS (SELECT 1 FROM uranus.event_type_link l
        JOIN uranus.event e ON e.uuid=l.event_uuid
        WHERE l.type_id=g.type_id AND l.genre_id=g.genre_id AND {PUBLIC_EVENT})
"""


EVENT_TYPES_SQL = f"""WITH types AS (
    SELECT DISTINCT ON(type_id) type_id,name FROM uranus.event_type
    WHERE NULLIF(trim(name),'') IS NOT NULL
    ORDER BY type_id,CASE iso_639_1 WHEN 'de' THEN 0 WHEN 'en' THEN 1 ELSE 2 END,
        iso_639_1 COLLATE "C" NULLS LAST,name COLLATE "C"
)
    SELECT t.type_id::text id,t.name label,t.name name FROM types t
    WHERE EXISTS (SELECT 1 FROM uranus.event_type_link l
        JOIN uranus.event e ON e.uuid=l.event_uuid
        WHERE l.type_id=t.type_id AND {PUBLIC_EVENT})
"""


async def load_taxonomy(connection: AsyncConnection) -> list[TaxonomyRow]:
    rows = list(
        (
            await connection.execute(
                text(f"""
        WITH types AS ({EVENT_TYPES_SQL}), genres AS ({GENRES_SQL}), entries AS (
          SELECT 'event_type' kind,t.id,t.label,
            (SELECT jsonb_agg(jsonb_build_object('language',l.iso_639_1,'label',l.name)
                ORDER BY l.iso_639_1 COLLATE "C", l.name COLLATE "C")
             FROM uranus.event_type l WHERE l.type_id::text=t.id
             AND l.iso_639_1 IS NOT NULL AND NULLIF(trim(l.name),'') IS NOT NULL) labels
          FROM types t
          UNION ALL
          SELECT 'genre' kind,g.id,g.label,
            (SELECT jsonb_agg(jsonb_build_object('language',l.iso_639_1,'label',l.name)
                ORDER BY l.iso_639_1 COLLATE "C", l.name COLLATE "C")
             FROM uranus.genre_type l WHERE l.type_id::text=split_part(g.id,':',1)
             AND l.genre_id::text=split_part(g.id,':',2)
             AND l.iso_639_1 IS NOT NULL AND NULLIF(trim(l.name),'') IS NOT NULL) labels
          FROM genres g
        ) SELECT kind,id,label,labels FROM entries ORDER BY kind,id LIMIT 4097
    """)
            )
        ).mappings()
    )
    if len(rows) > 4096:
        raise ValueError("taxonomy_vocabulary_overflow")
    return [
        TaxonomyRow(
            kind=r["kind"],
            id=r["id"],
            label=r["label"],
            labels=tuple(LocalizedLabel.model_validate(label) for label in r["labels"] or []),
        )
        for r in rows
    ]
