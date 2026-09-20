"""Validate a candidate admin vhost before installation. Never print nginx diagnostics."""

import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    candidate = Path(sys.argv[1]).resolve()
    if any(c in str(candidate) for c in '\n\r";{}'):
        return 1
    with tempfile.TemporaryDirectory(prefix="uranus-admin-nginx-") as directory:
        config = Path(directory) / "nginx.conf"
        config.write_text(
            "pid " + directory + "/nginx.pid;\nerror_log /dev/null;\nevents {}\nhttp {\n"
            "include /etc/nginx/mime.types;\n"
            "include /etc/nginx/conf.d/uranus-admin-ratelimit.conf;\n"
            'include "' + str(candidate.parent / "uranus-admin-logging.conf") + '";\n'
            'include "' + str(candidate) + '";\n}\n'
        )
        result = subprocess.run(
            ["/usr/sbin/nginx", "-t", "-c", str(config)], capture_output=True, timeout=20
        )
    print("Nginx candidate valid" if result.returncode == 0 else "Nginx candidate invalid")
    return result.returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired):
        raise SystemExit("Nginx candidate verification unavailable") from None
