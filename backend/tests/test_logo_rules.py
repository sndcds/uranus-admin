from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.repositories.quality_sources import SOURCE_QUERIES, Sources
from app.schemas.finding import FindingFilters
from app.services.checks import persisted_page, run_check
from app.services.quality.core import LOGO_IDENTIFIERS, evaluate_core
from tests.conftest import uid

NOW = datetime(2026, 9, 17, 12, tzinfo=UTC)


def logo_sources(kind, identifier="main_logo", mime_type="image/png", *, dangling=False):
    sources = Sources({kind: [] for kind in SOURCE_QUERIES})
    sources.rows[kind] = [{"uuid": uid(20), "name": "Logo owner", "org_uuid": None}]
    sources.rows["image"] = [
        {"uuid": uid(60), "mime_type": mime_type, "file_name": "misleading.png", "created_at": None}
    ]
    if identifier:
        sources.rows["image_link"] = [
            {
                "context": kind,
                "context_uuid": uid(20),
                "identifier": identifier,
                "pluto_image_uuid": uid(999) if dangling else uid(60),
            }
        ]
    return sources


@pytest.mark.parametrize("kind", ["venue", "organization"])
@pytest.mark.parametrize(
    "identifier,mime_type,dangling,missing,unsupported",
    [
        ("main_logo", "image/png", False, False, False),
        ("main_logo", "image/webp", False, False, False),
        ("main_logo", "IMAGE/PNG", False, False, False),
        ("main_logo", " image/webp ", False, False, False),
        ("main_logo", " IMAGE/JPEG ", False, False, True),
        (None, "image/png", False, True, False),
        ("avatar", "image/jpeg", False, True, False),
        ("dark_theme_logo", "image/png", False, True, False),
        ("main_logo", "image/png", True, True, False),
        ("main_logo", "image/jpeg", False, False, True),
        ("main_logo", "image/svg+xml", False, False, True),
        ("main_logo", "image/gif", False, False, True),
        ("main_logo", "image/avif", False, False, True),
        ("main_logo", None, False, False, False),
        ("main_logo", "", False, False, False),
        ("main_logo", "  ", False, False, False),
        ("dark_theme_logo", "image/jpeg", False, True, True),
        ("light_theme_logo", "image/jpeg", False, True, True),
    ],
)
def test_logo_contract(settings, kind, identifier, mime_type, dangling, missing, unsupported):
    sources = logo_sources(kind, identifier, mime_type, dangling=dangling)
    rule = f"{kind}_missing_logo"
    result = evaluate_core(rule, sources, settings, NOW)
    assert len(result.findings) == int(missing)
    assert result.covered == {(kind, str(uid(20)))}
    if missing:
        finding = result.findings[0]
        assert finding.id == f"{rule}:{kind}:{uid(20)}:main_logo"
        assert finding.field == "main_logo" and finding.severity == "warning"
        assert finding.metadata["expected_identifier"] == "main_logo"
        assert finding.message == (
            "Ort hat kein Hauptlogo." if kind == "venue" else "Organisation hat kein Hauptlogo."
        )
        assert (
            finding.action.href == f"/{'venues' if kind == 'venue' else 'organizations'}/{uid(20)}"
        )
    result = evaluate_core("logo_unsupported_format", sources, settings, NOW)
    assert len(result.findings) == int(unsupported)
    assert result.covered == {(kind, str(uid(20)))}
    if unsupported:
        finding = result.findings[0]
        assert finding.id == f"logo_unsupported_format:{kind}:{uid(20)}:{identifier}.mime_type"
        assert finding.field == f"{identifier}.mime_type" and finding.severity == "info"
        assert finding.message == "Logo verwendet kein PNG- oder WebP-Format."
        assert finding.metadata["identifier"] == identifier
        assert finding.metadata["mime_type"] == mime_type
        assert finding.metadata["allowed_mime_types"] == ["image/png", "image/webp"]
    broken = evaluate_core("image_link_without_image", sources, settings, NOW)
    assert len(broken.findings) == int(dangling)


@pytest.mark.parametrize("kind", ["venue", "organization"])
def test_variants_have_stable_distinct_identities(settings, kind):
    sources = logo_sources(kind, mime_type="image/jpeg")
    link = sources.rows["image_link"][0]
    sources.rows["image_link"] = [{**link, "identifier": name} for name in sorted(LOGO_IDENTIFIERS)]
    result = evaluate_core("logo_unsupported_format", sources, settings, NOW)
    assert len({finding.id for finding in result.findings}) == 3
    sources.rows["image_link"].reverse()
    assert {f.id for f in result.findings} == {
        f.id for f in evaluate_core("logo_unsupported_format", sources, settings, NOW).findings
    }
    assert not evaluate_core(f"{kind}_missing_logo", sources, settings, NOW).findings


@pytest.mark.parametrize(
    "kind,identifier",
    [
        ("venue", "main_photo"),
        ("venue", "gallery_photo_1"),
        ("venue", "gallery_photo_2"),
        ("venue", "gallery_photo_3"),
        ("event", "main"),
        ("event", "main_logo"),
        ("portal", "web_logo"),
        ("portal", "main_logo"),
    ],
)
def test_non_logos_are_excluded(settings, kind, identifier):
    sources = logo_sources("venue", identifier, "image/jpeg")
    sources.rows["image_link"][0]["context"] = kind
    assert not evaluate_core("logo_unsupported_format", sources, settings, NOW).findings


def test_missing_target_stays_in_existing_image_rule(settings):
    sources = logo_sources("venue", mime_type="image/jpeg")
    sources.rows["image_link"][0]["context_uuid"] = uid(999)
    assert not evaluate_core("logo_unsupported_format", sources, settings, NOW).findings
    assert len(evaluate_core("image_link_missing_target", sources, settings, NOW).findings) == 1


@pytest.mark.parametrize("kind,key", [("venue", 20), ("organization", 10)])
@pytest.mark.parametrize("scenario", ["missing", "format", "removed_variant"])
async def test_logo_resolution_and_incomplete_runs(
    admin_store, db_connection, settings, now, monkeypatch, kind, key, scenario
):
    from app.services.quality.engine import scan

    identifier = "dark_theme_logo" if scenario == "removed_variant" else "main_logo"
    link_sql = text(
        "INSERT INTO uranus.pluto_image_link "
        "(context,context_uuid,identifier,pluto_image_uuid) VALUES (:kind,:key,:identifier,:image)"
    )
    params = {"kind": kind, "key": uid(key), "identifier": identifier, "image": uid(60)}
    if scenario != "missing":
        await db_connection.execute(link_sql, params)
        await db_connection.execute(text("UPDATE uranus.pluto_image SET mime_type='image/jpeg'"))
    rule = f"{kind}_missing_logo" if scenario == "missing" else "logo_unsupported_format"
    filters = FindingFilters(rule=rule, entity_type=kind, entity_key=str(uid(key)))
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    item = (await persisted_page(admin_store, filters, now)).items[0]
    assert item.status == "open"
    assert item.severity == ("warning" if scenario == "missing" else "info")
    assert "published_soon" in item.priority_reasons
    if scenario == "missing":
        await db_connection.execute(link_sql, params)
    elif scenario == "format":
        await db_connection.execute(text("UPDATE uranus.pluto_image SET mime_type='image/webp'"))
    else:
        await db_connection.execute(text("DELETE FROM uranus.pluto_image_link"))

    async def incomplete(*args):
        return (await scan(*args))[:-1]

    async def failed(*args):
        results = await scan(*args)
        results[-1].success = False
        return results

    for replacement in (incomplete, failed):
        with monkeypatch.context() as patch:
            patch.setattr("app.services.checks.scan", replacement)
            assert (await run_check(db_connection, admin_store, settings)).status == "failed"
        assert (await persisted_page(admin_store, filters, now)).items[0].status == "open"
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    resolved = (await persisted_page(admin_store, filters, now)).items[0]
    assert resolved.id == item.id and resolved.status == "resolved" and resolved.resolved_at
    assert resolved.first_seen_at == item.first_seen_at


async def test_logo_summary_counts_filters_and_entity_details(
    admin_store, db_client, headers, database, settings, now
):
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.services.checks import persisted_counts

    # Commit synthetic source changes so the read-only HTTP connection sees them.
    engine = create_async_engine(database[0])
    try:
        async with engine.begin() as source:
            await source.execute(text("UPDATE uranus.pluto_image SET mime_type='image/jpeg'"))
            await source.execute(
                text(
                    "INSERT INTO uranus.pluto_image_link VALUES (:image,'venue',:owner,'main_logo')"
                ),
                {"image": uid(60), "owner": uid(20)},
            )
        async with engine.connect() as source, source.begin():
            await source.execute(text("SET TRANSACTION READ ONLY"))
            assert (await run_check(source, admin_store, settings)).status == "success"
        counts, _ = await persisted_counts(admin_store)
        assert counts.rule_counts["venue_missing_logo"] == 2
        assert counts.rule_counts["organization_missing_logo"] == 2
        assert counts.rule_counts["logo_unsupported_format"] == 1
        for rule, kind, key, section, severity in [
            ("venue_missing_logo", "venue", 21, "venues", "warning"),
            ("organization_missing_logo", "organization", 10, "organizations", "warning"),
            ("logo_unsupported_format", "venue", 20, "venues", "info"),
        ]:
            response = await db_client.get(
                "/api/v1/findings",
                headers=headers,
                params={"rule": rule, "entity_type": kind, "entity_key": str(uid(key))},
            )
            assert response.status_code == 200, response.text
            items = response.json()["items"]
            assert len(items) == 1 and items[0]["severity"] == severity
            assert items[0]["action"]["href"] == f"/{section}/{uid(key)}"
            detail = await db_client.get(f"/api/v1/{section}/{uid(key)}", headers=headers)
            assert detail.status_code == 200
            assert detail.json()["item"]["finding_count"] >= 1
        async with engine.begin() as source:
            await source.execute(text("UPDATE uranus.pluto_image SET mime_type='image/webp'"))
        async with engine.connect() as source, source.begin():
            assert (await run_check(source, admin_store, settings)).status == "success"
        counts, _ = await persisted_counts(admin_store)
        assert counts.rule_counts["logo_unsupported_format"] == 0
        assert counts.total == sum(counts.rule_counts.values())
    finally:
        async with engine.begin() as source:
            await source.execute(text("DELETE FROM uranus.pluto_image_link"))
            await source.execute(text("UPDATE uranus.pluto_image SET mime_type=NULL"))
        await engine.dispose()


@pytest.mark.integration
@pytest.mark.parametrize(
    "kind,key,section", [("venue", 20, "venues"), ("organization", 10, "organizations")]
)
async def test_multiple_logo_variants_persist_and_resolve_independently(
    admin_store, db_connection, settings, now, monkeypatch, kind, key, section
):
    from sqlalchemy import select

    from app.admin_tables import finding
    from app.services.checks import persisted_counts
    from app.services.quality.engine import scan

    rule = "logo_unsupported_format"
    variants = {
        "main_logo": (uid(1060), "image/jpeg"),
        "dark_theme_logo": (uid(1061), "image/jpeg"),
        "light_theme_logo": (uid(1062), "image/svg+xml"),
    }
    for identifier, (image_id, mime_type) in variants.items():
        await db_connection.execute(
            text(
                "INSERT INTO uranus.pluto_image (uuid,file_name,mime_type) VALUES (:id,:name,:mime)"
            ),
            {"id": image_id, "name": f"{identifier}.png", "mime": mime_type},
        )
        await db_connection.execute(
            text(
                "INSERT INTO uranus.pluto_image_link "
                "(context,context_uuid,identifier,pluto_image_uuid) "
                "VALUES (:kind,:key,:variant,:image)"
            ),
            {"kind": kind, "key": uid(key), "variant": identifier, "image": image_id},
        )
    filters = FindingFilters(rule=rule, entity_type=kind, entity_key=str(uid(key)))

    async def stored_rows():
        async with admin_store.begin():
            return (
                (
                    await admin_store.execute(
                        select(finding).where(
                            finding.c.rule == rule,
                            finding.c.entity_type == kind,
                            finding.c.entity_key == str(uid(key)),
                        )
                    )
                )
                .mappings()
                .all()
            )

    async def assert_states(expected):
        rows = await stored_rows()
        assert len(rows) == 3
        assert {row["field"]: row["status"] for row in rows} == expected
        for row in rows:
            assert row["id"] == f"{rule}:{kind}:{uid(key)}:{row['field']}"
            assert row["severity"] == "info"
            assert (row["resolved_at"] is not None) == (row["status"] == "resolved")
        counts, _ = await persisted_counts(admin_store)
        assert counts.rule_counts[rule] == sum(state == "open" for state in expected.values())

    # This must insert three real rows under the existing finding_identity constraint.
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    expected = {f"{identifier}.mime_type": "open" for identifier in variants}
    await assert_states(expected)
    original = (await persisted_page(admin_store, filters, now)).items
    assert len(original) == 3
    assert all(item.action.href == f"/{section}/{uid(key)}" for item in original)
    first_seen = {item.id: item.first_seen_at for item in original}
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    await assert_states(expected)

    async def failed(*args):
        raise RuntimeError("Synthetic source scan failure")

    async def incomplete(*args):
        return (await scan(*args))[:-1]

    async def unsuccessful_rule(*args):
        results = await scan(*args)
        results[-1].success = False
        return results

    async def assert_failed_scans_preserve_states():
        for replacement in (failed, incomplete, unsuccessful_rule):
            with monkeypatch.context() as patch:
                patch.setattr("app.services.checks.scan", replacement)
                assert (await run_check(db_connection, admin_store, settings)).status == "failed"
            await assert_states(expected)

    await db_connection.execute(
        text("UPDATE uranus.pluto_image SET mime_type='image/webp' WHERE uuid=:image"),
        {"image": variants["dark_theme_logo"][0]},
    )
    await assert_failed_scans_preserve_states()
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    expected["dark_theme_logo.mime_type"] = "resolved"
    await assert_states(expected)

    await db_connection.execute(
        text(
            "DELETE FROM uranus.pluto_image_link WHERE context=:kind AND context_uuid=:key "
            "AND identifier='light_theme_logo'"
        ),
        {"kind": kind, "key": uid(key)},
    )
    await assert_failed_scans_preserve_states()
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    expected["light_theme_logo.mime_type"] = "resolved"
    await assert_states(expected)
    final = (await persisted_page(admin_store, filters, now)).items
    assert {item.id: item.first_seen_at for item in final} == first_seen
