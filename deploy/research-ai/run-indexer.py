"""Server A operator wrapper: expose only required reader settings to the pilot process."""

import os
import runpy

from dotenv import dotenv_values

runtime = dotenv_values("/etc/uranus-admin/runtime.env")
for key in ("DATABASE_URL", "ADMIN_DATABASE_URL", "URANUS_TIMESTAMP_TIMEZONE", "EVENT_TIMEZONE"):
    if runtime.get(key):
        os.environ[key] = runtime[key]
for key, value in dotenv_values("/etc/uranus-research-ai/client.env").items():
    if (
        key
        in {
            "QDRANT_URL",
            "QDRANT_API_KEY",
            "EMBEDDING_URL",
            "EMBEDDING_API_KEY",
            "EMBEDDING_TIMEOUT_SECONDS",
            "QDRANT_COLLECTION_PREFIX",
        }
        and value
    ):
        os.environ[key] = value
os.environ["APP_ENV"] = "production"
runpy.run_module("app.research.vector_index", run_name="__main__")
