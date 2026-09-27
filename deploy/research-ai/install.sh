#!/bin/sh
# Server B only. Reviewed, explicit installation; never touches the Uranus/admin deployment.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run with sudo on Server B' >&2; exit 1; }
cd "$(dirname "$0")"
nginx -t
command -v nft >/dev/null
docker compose version >/dev/null
test -f /etc/letsencrypt/live/nominatim.oklabflensburg.de/fullchain.pem
# Existing dedicated configuration is never overwritten implicitly.
test ! -e /etc/uranus-research-ai
test ! -e /etc/nginx/conf.d/uranus-research-ai.conf
install -d -m 0750 /etc/uranus-research-ai
install -d -o 10001 -g 10001 -m 0750 /srv/qdrant/storage /srv/qdrant/snapshots /srv/models
python3 - <<'PY'
import os, secrets
from pathlib import Path
os.umask(0o077)
root=Path('/etc/uranus-research-ai')
qkey=secrets.token_urlsafe(48)
ekey=secrets.token_urlsafe(48)
(root/'qdrant.yaml').write_text('service:\n  api_key: "'+qkey+'"\n  max_request_size_mb: 2\nstorage:\n  snapshots_path: /qdrant/snapshots\n  performance:\n    max_search_threads: 2\n')
(root/'embedding.key').write_text(ekey+'\n')
# This file is transferred only to A over SSH and is never logged or committed.
(root/'client.env').write_text('QDRANT_URL=https://nominatim.oklabflensburg.de:7443\nQDRANT_API_KEY='+qkey+'\nEMBEDDING_URL=https://nominatim.oklabflensburg.de:7444\nEMBEDDING_API_KEY='+ekey+'\nEMBEDDING_TIMEOUT_SECONDS=600\n')
for name in ('qdrant.yaml','embedding.key'):
    os.chown(root/name,10001,10001)
PY
install -m 0644 guard.nft /etc/uranus-research-ai/guard.nft
install -m 0644 uranus-research-ai-guard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now uranus-research-ai-guard.service
install -m 0644 ingress.conf /etc/nginx/conf.d/uranus-research-ai.conf
nginx -t
systemctl reload nginx
echo 'Ingress and private storage configured; build/prefetch/start explicitly using operations.md.'
