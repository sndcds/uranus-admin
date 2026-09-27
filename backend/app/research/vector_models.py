"""Reviewed, pinned retrieval models; no implicit production model or remote input IDs."""

from dataclasses import dataclass

from app.research.vector_documents import CHUNK_VERSION


@dataclass(frozen=True)
class Model:
    name: str
    revision: str
    dimensions: int
    license: str
    prefix: str

    @property
    def repository(self) -> str:
        return "jinaai/jina-embeddings-v3-hf" if self.name.startswith("jinaai/") else self.name

    @property
    def weights_revision(self) -> str:
        return (
            "d18862d9a48706220815554fac3ebb4dfa46fc28"
            if self.name.startswith("jinaai/")
            else self.revision
        )

    @property
    def version(self) -> str:
        return (
            f"{self.weights_revision}:native-transformers5.17.0-retrieval-normalized-f32:"
            f"{CHUNK_VERSION}"
        )


# Official model repositories/model-card license metadata, checked 2026-09-27.
MODELS = {
    "e5-small": Model(
        "intfloat/multilingual-e5-small",
        "614241f622f53c4eeff9890bdc4f31cfecc418b3",
        384,
        "MIT",
        "passage: ",
    ),
    "e5-base": Model(
        "intfloat/multilingual-e5-base",
        "d128750597153bb5987e10b1c3493a34e5a4502a",
        768,
        "MIT",
        "passage: ",
    ),
    "jina-v3": Model(
        "jinaai/jina-embeddings-v3",
        "ab036b023d30b4d1138c4c3bfa9f0c445ab455d6",
        1024,
        "CC-BY-NC-4.0",
        "",
    ),
}
