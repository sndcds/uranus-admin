"""Explicit one-model-at-a-time prefetch; only pinned data/weights, never repository code."""

import argparse

from huggingface_hub import snapshot_download

from app.research.vector_models import MODELS

parser = argparse.ArgumentParser()
parser.add_argument("model", choices=tuple(MODELS))
parser.add_argument("--noncommercial-jina", action="store_true")
args = parser.parse_args()
if args.model == "jina-v3" and not args.noncommercial_jina:
    parser.error("Noncommercial license acknowledgment required")
model = MODELS[args.model]
snapshot_download(
    model.repository,
    revision=model.weights_revision,
    max_workers=1,
    allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt", "README.md", "LICENSE*"],
)
print("model_cached", args.model, model.weights_revision)
