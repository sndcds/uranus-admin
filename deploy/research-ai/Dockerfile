FROM ghcr.io/astral-sh/uv:0.12.5@sha256:db2d5999728c5837e1bf9ba278ee6b05cef1e95e82a20e27b0c915cb4478b9d7 AS uv
FROM python:3.13.15-slim-bookworm@sha256:3e2de9c40ca4e3d73240059f9d48baff27908f10293e985a2f382a0378e6df4a
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/encoder
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --group embedding --no-install-project && uv cache clean
COPY backend/app ./app
COPY deploy/research-ai/encoder.py deploy/research-ai/prefetch.py ./
ENV PATH="/opt/encoder/.venv/bin:$PATH" HF_HOME=/models HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
USER 10001:10001
CMD ["uvicorn", "encoder:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--limit-concurrency", "4", "--timeout-keep-alive", "5"]
