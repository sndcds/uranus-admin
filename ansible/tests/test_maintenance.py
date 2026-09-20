"""Static asset contracts and a real, isolated Nginx HTTP fixture (no production access)."""

import hashlib
import html
import http.client
import http.server
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from test_deployment import ROLE

DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
TEMPLATES = Environment(loader=FileSystemLoader(ROLE / "templates"), undefined=StrictUndefined)


class MaintenanceStaticTests(unittest.TestCase):
    def test_accessible_without_javascript_and_all_operator_copy_is_escaped(self):
        values = dict(DEFAULTS)
        for value in ("<script>alert(1)</script>", '" onclick="alert(1)', "& < >"):
            for key in ("title", "message", "window"):
                values["ua_maintenance_public_" + key] = value
            rendered = TEMPLATES.get_template("maintenance.html.j2").render(values)
            self.assertNotIn(value, rendered)
            # MarkupSafe uses numeric quotation escapes; both forms decode identically.
            self.assertEqual(html.unescape(rendered).count(value), 4)
            for required in (
                '<html lang="de">',
                "<title>",
                "<main ",
                "<h1>",
                'aria-hidden="true"',
                "prefers-reduced-motion: reduce",
            ):
                self.assertIn(required, rendered)
            self.assertNotIn("https://", rendered)
            self.assertNotIn("http://", rendered)
            self.assertNotIn("| safe", (ROLE / "templates/maintenance.html.j2").read_text())
        rendered = TEMPLATES.get_template("maintenance.html.j2").render(DEFAULTS)
        self.assertNotIn("Wartungsfenster", rendered)
        self.assertIn(DEFAULTS["ua_maintenance_public_message"], rendered)
        self.assertNotIn(
            "ua_maintenance_window", (ROLE / "templates/maintenance.html.j2").read_text()
        )

    def test_preparation_and_marker_operations_are_idempotent(self):
        from test_system_recovery import ActivationIntegrationTests

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            role = root / "roles/uranus_admin"
            shutil.copytree(ROLE, role)
            tasks = yaml.safe_load((role / "tasks/maintenance_prepare.yml").read_text())
            ActivationIntegrationTests.adapt_host_io(tasks)
            (role / "tasks/maintenance_prepare.yml").write_text(yaml.safe_dump(tasks))
            enable = yaml.safe_load((role / "tasks/maintenance_enable.yml").read_text())[0][
                "block"
            ][1]
            disable = yaml.safe_load((role / "tasks/maintenance_disable.yml").read_text())[0][
                "block"
            ][0]
            ActivationIntegrationTests.adapt_host_io([enable, disable])
            enable["register"] = "marker_enabled"
            disable["register"] = "marker_disabled"
            stat = {
                "ansible.builtin.stat": {"path": "{{ ua_maintenance_root }}/maintenance.html"},
                "register": "page_stat",
            }
            steps = [
                {"ansible.builtin.import_tasks": "maintenance_prepare.yml"},
                stat,
                {"ansible.builtin.set_fact": {"first_mtime": "{{ page_stat.stat.mtime }}"}},
                {"ansible.builtin.import_tasks": "maintenance_prepare.yml"},
                stat,
                {
                    "ansible.builtin.assert": {
                        "that": [
                            "page_stat.stat.mtime == first_mtime",
                            "page_stat.stat.mode == '0644'",
                        ]
                    }
                },
                enable,
                enable,
                {"ansible.builtin.assert": {"that": "not marker_enabled.changed"}},
                disable,
                disable,
                {"ansible.builtin.assert": {"that": "not marker_disabled.changed"}},
            ]
            (role / "tasks/main.yml").write_text(yaml.safe_dump(steps))
            play = [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {
                        "ansible_python_interpreter": sys.executable,
                        "ansible_remote_tmp": str(root / "remote"),
                        "ua_maintenance_root": str(root / "maintenance"),
                        "ua_maintenance_marker": str(root / "maintenance/enabled"),
                    },
                    "roles": ["uranus_admin"],
                }
            ]
            (root / "play.yml").write_text(yaml.safe_dump(play))
            (root / "ansible.cfg").write_text(
                "[defaults]\nroles_path=" + str(root / "roles") + "\n"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ansible.cli.playbook",
                    "-i",
                    "localhost,",
                    str(root / "play.yml"),
                ],
                env={
                    **os.environ,
                    "ANSIBLE_CONFIG": str(root / "ansible.cfg"),
                    "ANSIBLE_LOCAL_TEMP": str(root / "tmp"),
                },
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((root / "maintenance/enabled").exists())

    def test_local_runtime_integrity_license_and_shape_only_animation(self):
        assets = ROLE / "files/maintenance"
        self.assertEqual(
            hashlib.sha256((assets / "lottie.min.js").read_bytes()).hexdigest(),
            "9588432bec30c8ef8200bac4a67d8aaad881047bc2a6c9fa624d90ec96402410",
        )
        self.assertIn("The MIT License (MIT)", (assets / "LICENSE.lottie-web.txt").read_text())
        animation = json.loads((assets / "maintenance.json").read_text())
        self.assertEqual(animation["assets"], [])
        self.assertTrue(all(layer["ty"] == 4 for layer in animation["layers"]))
        self.assertLess((assets / "maintenance.json").stat().st_size, 6000)
        self.assertNotRegex(json.dumps(animation), r"https?://|data:")
        script = (assets / "maintenance.js").read_text()
        self.assertIn("animation.pause()", script)
        self.assertIn("!motion.matches", script)


class ProxyFixture(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(("proxied " + self.path).encode())

    def log_message(self, *_):
        pass


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(shutil.which("nginx") and shutil.which("openssl"), "nginx/openssl absent")
class MaintenanceNginxTests(unittest.TestCase):
    def test_marker_switches_real_proxy_and_headers_without_upstream_or_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o755)
            assets = root / "maintenance/assets"
            shutil.copytree(ROLE / "files/maintenance", assets)
            values = {
                **DEFAULTS,
                "ua_maintenance_root": str(root / "maintenance"),
                "ua_maintenance_marker": str(root / "maintenance/enabled"),
            }
            (root / "maintenance/maintenance.html").write_text(
                TEMPLATES.get_template("maintenance.html.j2").render(values)
            )
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-keyout",
                    str(root / "key.pem"),
                    "-out",
                    str(root / "cert.pem"),
                    "-subj",
                    "/CN=localhost",
                    "-days",
                    "1",
                ],
                check=True,
                capture_output=True,
            )
            upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ProxyFixture)
            thread = threading.Thread(target=upstream.serve_forever, daemon=True)
            thread.start()
            https_port, http_port = unused_port(), unused_port()
            site = TEMPLATES.get_template("nginx-site.conf.j2").render(values)
            for old, new in {
                "listen 80;": f"listen 127.0.0.1:{http_port};",
                "listen [::]:80;": "",
                "listen 443 ssl http2;": f"listen 127.0.0.1:{https_port} ssl;",
                "listen [::]:443 ssl http2;": "",
                "/etc/letsencrypt/live/admin.kulturbytes.de/fullchain.pem": str(root / "cert.pem"),
                "/etc/letsencrypt/live/admin.kulturbytes.de/privkey.pem": str(root / "key.pem"),
                "/var/log/nginx/uranus-admin-access.log": str(root / "access.log"),
                "/var/log/nginx/uranus-admin-error.log": str(root / "error.log"),
                "127.0.0.1:3011": f"127.0.0.1:{upstream.server_port}",
            }.items():
                site = site.replace(old, new)
            config = (
                f"pid {root}/nginx.pid; error_log stderr; events {{}} http {{\n"
                "limit_req_zone $binary_remote_addr zone=uranus_admin_general:10m rate=10r/s;\n"
                "limit_req_zone $binary_remote_addr zone=uranus_admin_api:10m rate=5r/s;\n"
                "limit_conn_zone $binary_remote_addr zone=uranus_admin_conn:10m;\n"
                + TEMPLATES.get_template("nginx-logging.conf.j2").render()
                + site
                + "\n}"
            )
            (root / "nginx.conf").write_text(config)
            process = subprocess.Popen(
                [
                    shutil.which("nginx"),
                    "-p",
                    directory,
                    "-c",
                    str(root / "nginx.conf"),
                    "-g",
                    "daemon off;",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Trust the generated fixture certificate; never disable certificate validation.
            context = ssl.create_default_context(cafile=str(root / "cert.pem"))

            def get(path):
                conn = http.client.HTTPSConnection(
                    "localhost", https_port, context=context, timeout=3
                )
                try:
                    conn.request("GET", path)
                    response = conn.getresponse()
                    return response.status, dict(response.getheaders()), response.read().decode()
                finally:
                    conn.close()

            try:
                for _attempt in range(50):
                    try:
                        status, _, body = get("/login")
                        break
                    except ConnectionRefusedError:
                        time.sleep(0.05)
                else:
                    self.fail("Fixture nginx did not start")
                self.assertEqual((status, body), (200, "proxied /login"))
                for path in ("/", "/api/admin/auth/session", "/_nuxt/app.js"):
                    self.assertEqual(get(path)[2], "proxied " + path)
                for name in ("lottie.min.js", "maintenance.json", "maintenance.js", "unknown"):
                    self.assertEqual(get("/__maintenance_assets/" + name)[0], 404)
                self.assertEqual(get("/__maintenance.html")[0], 404)
                Path(values["ua_maintenance_marker"]).write_text("enabled\n")
                upstream.shutdown()
                upstream.server_close()
                for path in ("/", "/login", "/api/admin/auth/session", "/_nuxt/app.js"):
                    status, headers, body = get(path)
                    self.assertEqual(status, 503)
                    self.assertIn('id="kulturbytes-maintenance"', body)
                    self.assertEqual(headers["Retry-After"], "300")
                    self.assertEqual(headers["Cache-Control"], "no-store")
                    self.assertEqual(headers["X-Robots-Tag"], "noindex, nofollow, noarchive")
                    self.assertEqual(headers["X-Frame-Options"], "DENY")
                    self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                    self.assertIn("max-age=31536000", headers["Strict-Transport-Security"])
                    csp = headers["Content-Security-Policy"]
                    self.assertIn("default-src 'none'", csp)
                    self.assertIn("connect-src 'self'", csp)
                    self.assertIn("script-src 'self';", csp)
                    self.assertNotIn("https:", csp)
                    self.assertNotIn("unsafe-eval", csp)
                for name in ("lottie.min.js", "maintenance.json", "maintenance.js"):
                    status, _, body = get("/__maintenance_assets/" + name)
                    self.assertEqual(status, 200)
                    self.assertEqual(body, (assets / name).read_text())
                self.assertEqual(get("/__maintenance_assets/unknown")[0], 404)
                upstream = http.server.ThreadingHTTPServer(
                    ("127.0.0.1", upstream.server_port), ProxyFixture
                )
                thread = threading.Thread(target=upstream.serve_forever, daemon=True)
                thread.start()
                Path(values["ua_maintenance_marker"]).unlink()
                self.assertEqual(get("/login")[2], "proxied /login")
                self.assertEqual(get("/__maintenance_assets/lottie.min.js")[0], 404)
                self.assertEqual(get("/__maintenance.html")[0], 404)
            finally:
                process.terminate()
                _, err = process.communicate(timeout=10)
                upstream.shutdown()
                upstream.server_close()
                self.assertEqual(process.returncode, 0, err.decode())
