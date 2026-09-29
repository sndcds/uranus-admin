"""Internal CPU-only service. Fixed model IDs; no URL, code or shell input."""

import asyncio
import hmac
import json
import logging
import os
import resource
import time
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from app.logging import configure_logging
from app.research.vector_documents import Section, chunk_sections
from app.research.vector_models import MODELS


class InputDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: UUID
    sections: list[Section] = Field(min_length=1, max_length=1000)


class ChunkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Literal["e5-small", "e5-base", "jina-v3"]
    documents: list[InputDocument] = Field(min_length=1, max_length=4)


class EmbedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Literal["e5-small", "e5-base", "jina-v3"]
    texts: list[str] = Field(min_length=1, max_length=2)
    kind: Literal["query", "passage"]


class Runtime:
    def __init__(self):
        self.key = None
        self.model = None
        self.tokenizer = None

    def load(self, key):
        if self.key == key:
            return
        if key == "jina-v3" and os.environ.get("JINA_NONCOMMERCIAL") != "1":
            raise ValueError("license_acknowledgment_required")
        import gc

        import torch
        from transformers import AutoModel, AutoTokenizer

        torch.set_num_threads(2)
        self.model = None
        self.tokenizer = None
        self.key = None
        gc.collect()
        spec = MODELS[key]
        self.tokenizer = AutoTokenizer.from_pretrained(
            spec.repository,
            revision=spec.weights_revision,
            trust_remote_code=False,
            local_files_only=True,
        )
        self.model = AutoModel.from_pretrained(
            spec.repository,
            revision=spec.weights_revision,
            trust_remote_code=False,
            local_files_only=True,
            dtype=torch.float32,
            use_safetensors=True,
        )
        if key == "jina-v3":
            for task in ("retrieval_query", "retrieval_passage"):
                # Cache prefetch is explicit; runtime has offline mode and no download path.
                self.model.load_adapter(
                    spec.repository,
                    adapter_name=task,
                    adapter_kwargs={
                        "subfolder": task,
                        "revision": spec.weights_revision,
                        "local_files_only": True,
                    },
                )
        self.model.eval()
        self.key = key

    def count(self, value):
        return len(self.tokenizer(value, add_special_tokens=True, truncation=False)["input_ids"])

    def chunks(self, body):
        self.load(body.model)
        spec = MODELS[body.model]
        return {
            "embedding_version": spec.version,
            "documents": [
                {
                    "entity_id": str(d.entity_id),
                    "chunks": [
                        c.model_dump(mode="json", exclude={"contexts"} if not c.contexts else set())
                        for c in chunk_sections(d.sections, self.count, prefix=spec.prefix)
                    ],
                }
                for d in body.documents
            ],
        }

    def embed(self, body):
        import torch

        self.load(body.model)
        started, cpu = time.perf_counter(), time.process_time()
        texts = [
            ("query: " + t) if body.kind == "query" and body.model.startswith("e5-") else t
            for t in body.texts
        ]
        if any(len(t) > 200_000 or self.count(t) > 480 for t in texts):
            raise ValueError("token_limit")
        if (
            body.model.startswith("e5-")
            and body.kind == "passage"
            and any(not t.startswith("passage: ") for t in texts)
        ):
            raise ValueError("passage_prefix_required")
        if body.model == "jina-v3":
            self.model.set_adapter("retrieval_" + body.kind)
        encoded = self.tokenizer(texts, padding=True, truncation=False, return_tensors="pt")
        with torch.inference_mode():
            output = self.model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1)
            vectors = torch.nn.functional.normalize(
                (output * mask).sum(1) / mask.sum(1), p=2, dim=1
            )
        return {
            "embedding_version": MODELS[body.model].version,
            "vectors": vectors.tolist(),
            "metrics": {
                "wall_seconds": time.perf_counter() - started,
                "cpu_seconds": time.process_time() - cpu,
                "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            },
        }


def create_app(runtime=None, key=None):
    configure_logging("INFO")
    runtime = runtime or Runtime()
    key = key or Path(os.environ["EMBEDDING_KEY_FILE"]).read_text().strip()
    if len(key) < 32:
        raise ValueError("invalid_service_key")
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    lock = asyncio.Lock()
    failures = {"count": 0}

    @app.get("/health")
    async def health():
        return {"status": "ok", "failed_requests": failures["count"]}

    @app.post("/{operation}")
    async def operation(operation: str, request: Request):
        if not hmac.compare_digest(
            request.headers.get("authorization", "").encode(), ("Bearer " + key).encode()
        ):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if operation not in {"chunks", "embed"}:
            return JSONResponse({"error": "not_found"}, status_code=404)
        if lock.locked():
            return JSONResponse({"error": "busy"}, status_code=429)
        async with lock:
            try:
                data = bytearray()
                async with asyncio.timeout(10):
                    async for part in request.stream():
                        data.extend(part)
                        if len(data) > 2 * 1024 * 1024:
                            return JSONResponse({"error": "body_limit"}, status_code=413)
                body = (ChunkInput if operation == "chunks" else EmbedInput).model_validate(
                    json.loads(data)
                )
                result = await run_in_threadpool(getattr(runtime, operation), body)
                return JSONResponse(result)
            except (ValidationError, ValueError, TimeoutError):
                failures["count"] += 1
                return JSONResponse({"error": "invalid_request"}, status_code=422)
            except Exception as exc:
                failures["count"] += 1
                logging.getLogger("admin.encoder").error(
                    "encoder_failed", extra={"error_type": type(exc).__name__}
                )
                return JSONResponse({"error": "encoder_unavailable"}, status_code=503)

    return app
