"""Conservative taxonomy matching; IDs always come from source projections."""

from unittest.mock import AsyncMock, Mock

import pytest

from app.errors import APIError
from app.repositories import research_resolution as resolver


@pytest.fixture
def source():
    connection = AsyncMock()
    result = Mock()
    connection.execute.return_value = result
    result.mappings.return_value = []
    return connection, result


@pytest.mark.parametrize(
    "query,label",
    [
        ("Konzert", "Konzert"),
        ("Konzerte", "Konzert"),
        ("Konzerten", "Konzert"),
        ("Workshops", "Workshop"),
        ("Lesungen", "Lesung"),
        ("Ausstellungen", "Ausstellung"),
        ("Festivals", "Festival"),
        ("Vorträge", "Vortrag"),
        ("Vorträgen", "Vortrag"),
        ("Führungen", "Führung"),
        ("Stadtführungen", "Stadtführung"),
        ("Seminare", "Seminar"),
        ("Konferenzen", "Konferenz"),
        ("Versammlungen", "Versammlung"),
        ("  KONZERTEN\t", "Konzert"),
        ("Fu\u0308hrungen", "Führung"),
        ("Theater\t &   Bühne", "Theater & Bühne"),
        ("Straße", "STRASSE"),
        ("Ｓｅｍｉｎａｒ", "Seminar"),
    ],
)
async def test_inflections_resolve_only_to_loaded_canonical_rows(settings, source, query, label):
    connection, result = source
    result.mappings.return_value = [{"id": "123", "label": label}]
    choices = await resolver.candidates(connection, "event_type", query, settings)
    assert [(c.id, c.label) for c in choices] == [("123", label)]
    result.mappings.return_value = []
    assert await resolver.candidates(connection, "event_type", query, settings) == []


@pytest.mark.parametrize("dash", ["‐", "‑", "‒", "–", "—", "−"])
async def test_genre_typography(settings, source, dash):
    connection, result = source
    result.mappings.return_value = [{"id": "1:1004", "label": "Singer-songwriter"}]
    choices = await resolver.candidates(connection, "genre", f"Singer{dash}songwriter", settings)
    assert [(c.id, c.label) for c in choices] == [("1:1004", "Singer-songwriter")]


@pytest.mark.parametrize(
    "query,labels,expected",
    [
        ("Konzerte", ["Konzert", "Konzerte"], ["1"]),
        ("Konzert", ["Konzerte", "Konzert"], ["1"]),
        ("Konferenzen", ["Konferenz", "Konferenzen"], ["1"]),
        ("Führung", ["Fu\u0308hrung", "Führung"], ["1"]),
        ("Konzerte", ["Konzert", "Konzerten"], ["0", "1"]),
        ("Konzerte", ["Konzert", "Konzert"], ["0", "1"]),
        ("Theater  & Bühne", ["Theater & Bühne", "Theater\t& Bühne"], ["0", "1"]),
    ],
)
async def test_exact_priority_and_normalized_ambiguity(settings, source, query, labels, expected):
    connection, result = source
    result.mappings.return_value = [
        {"id": str(i), "label": label} for i, label in enumerate(labels)
    ]
    choices = await resolver.candidates(connection, "event_type", query, settings)
    assert [c.id for c in choices] == expected
    resolution = resolver.Resolution()
    resolution.select("event_type_queries", query, choices)
    if len(expected) > 1:
        assert resolution.clarification.reason == "ambiguous"
    else:
        assert resolution.clarification is None


@pytest.mark.parametrize(
    "query",
    ["Konz", "Jazz-Konzerte", "Konzert extra", "Konzertx", "Koncerte", "Unknown", "1", "%", "_"],
)
async def test_no_substring_fuzzy_or_id_resolution(settings, source, query):
    connection, result = source
    result.mappings.return_value = [{"id": "1", "label": "Konzert"}]
    choices = await resolver.candidates(connection, "event_type", query, settings)
    resolution = resolver.Resolution()
    assert resolution.select("event_type_queries", query, choices) is None
    assert resolution.clarification.reason == "no_match"


async def test_candidate_cap_does_not_hide_ambiguity_or_vocabulary_overflow(settings, source):
    connection, result = source
    result.mappings.return_value = [{"id": str(i), "label": "Konzert"} for i in range(6)]
    assert len(await resolver.candidates(connection, "event_type", "Konzerte", settings)) == 5
    result.mappings.return_value = [{"id": str(i), "label": "Konzert"} for i in range(4097)]
    with pytest.raises(APIError) as exc:
        await resolver.candidates(connection, "event_type", "Konzert", settings)
    assert exc.value.code == "research_execution_unavailable"


@pytest.mark.parametrize("kind", ["venue", "organization", "area", "category"])
async def test_other_resolution_paths_do_not_use_taxonomy_normalization(
    settings, source, monkeypatch, kind
):
    connection, _ = source
    normalize = Mock(side_effect=AssertionError("Taxonomy-only normalization"))
    monkeypatch.setattr(resolver, "taxonomy_forms", normalize)
    monkeypatch.setattr(resolver, "taxonomy_label", normalize)
    await resolver.candidates(connection, kind, " Konzerte ", settings)
    statement, params = connection.execute.call_args.args
    assert params["exact"] == "Konzerte"
    assert "lower(trim(label))=lower(:exact)" in str(statement)
    assert ("ILIKE" in str(statement)) == (kind != "category")
    normalize.assert_not_called()
