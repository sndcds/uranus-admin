"""Closed, bounded taxonomy index documents. No query aliases or source identities invented."""

import hashlib
import json
from typing import Annotated, Final, Literal, Self
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.research.vector_models import MODELS

COLLECTION = "kulturbytes_event_taxonomy_jina_v3_v1"
OWNER: Final = "kulturbytes-taxonomy-v1"
VERSION: Final = "taxonomy-public-v1"
MODEL = MODELS["jina-v3"]
Kind = Literal["event_type", "genre"]
Label = Annotated[str, Field(min_length=1, max_length=500)]
Identity = Annotated[str, Field(pattern=r"^[0-9]+(?::[0-9]+)?$", max_length=32)]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class LocalizedLabel(Closed):
    language: str = Field(pattern=r"^[a-z]{2,3}$")
    label: Label


class TaxonomyRow(Closed):
    kind: Kind
    id: Identity
    label: Label
    labels: tuple[LocalizedLabel, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def identity(self) -> Self:
        if (":" in self.id) != (self.kind == "genre") or self.id.endswith(":0"):
            raise ValueError("invalid_taxonomy_identity")
        return self


class TaxonomyVectorDocument(Closed):
    key: str = Field(max_length=48)
    kind: Kind
    type_id: str = Field(pattern=r"^[0-9]+$", max_length=16)
    genre_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$", max_length=16)
    canonical_label: Label
    language: str = Field(pattern=r"^[a-z]{2,3}$")
    parent_label: Label | None = None
    labels: tuple[LocalizedLabel, ...] = Field(max_length=64)
    embedding_text: str = Field(min_length=1, max_length=8000)

    @property
    def identity(self) -> str:
        return f"{self.type_id}:{self.genre_id}" if self.genre_id else self.type_id

    @property
    def point_id(self) -> str:
        return str(uuid5(NAMESPACE_URL, f"{COLLECTION}/{self.key}"))

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.key != f"{self.kind}:{self.identity}" or (self.kind == "genre") != bool(
            self.genre_id
        ):
            raise ValueError("invalid_taxonomy_identity")
        if (self.kind == "genre") != (self.parent_label is not None):
            raise ValueError("invalid_taxonomy_parent")
        return self


class TaxonomyPayload(TaxonomyVectorDocument):
    index_owner: Literal["kulturbytes-taxonomy-v1"]
    document_schema_version: Literal["taxonomy-public-v1"]
    embedding_model: str
    embedding_version: str
    corpus_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if self.embedding_model != MODEL.name or self.embedding_version != MODEL.version:
            raise ValueError("taxonomy_model_mismatch")
        return self


def documents(rows: list[TaxonomyRow]) -> list[TaxonomyVectorDocument]:
    if len(rows) > 4096 or len({(r.kind, r.id) for r in rows}) != len(rows):
        raise ValueError("invalid_taxonomy_snapshot")
    types = {r.id: r for r in rows if r.kind == "event_type"}
    result = []
    for row in sorted(rows, key=lambda r: (r.kind, r.id)):
        type_id, _, genre_id = row.id.partition(":")
        parent = types.get(type_id)
        if parent is None:
            raise ValueError("missing_taxonomy_parent")
        labels = tuple(sorted(set(row.labels), key=lambda label: (label.language, label.label)))
        languages = [label.language for label in labels if label.label == row.label]
        language = (
            "de"
            if "de" in languages
            else "en"
            if "en" in languages
            else next(iter(languages), "und")
        )
        parts = [
            row.label + ".",
            "Veranstaltungstyp."
            if row.kind == "event_type"
            else f"Genre innerhalb von {parent.label}.",
        ]
        parts.extend(f"{label.language}: {label.label}." for label in labels)
        if row.kind == "event_type":
            children = sorted(
                r.label for r in rows if r.kind == "genre" and r.id.split(":")[0] == row.id
            )
            if children:
                parts.append("Zugehörige Genres: " + ", ".join(children) + ".")
        result.append(
            TaxonomyVectorDocument(
                key=f"{row.kind}:{row.id}",
                kind=row.kind,
                type_id=type_id,
                genre_id=genre_id or None,
                canonical_label=row.label,
                language=language,
                parent_label=parent.label if row.kind == "genre" else None,
                labels=labels,
                embedding_text="\n".join(parts),
            )
        )
    return result


def corpus_hash(docs: list[TaxonomyVectorDocument]) -> str:
    value = json.dumps(
        [d.model_dump(mode="json") for d in docs], ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(value.encode()).hexdigest()


def index_payload(document: TaxonomyVectorDocument, digest: str) -> TaxonomyPayload:
    return TaxonomyPayload(
        **document.model_dump(),
        index_owner=OWNER,
        document_schema_version=VERSION,
        embedding_model=MODEL.name,
        embedding_version=MODEL.version,
        corpus_hash=digest,
    )
