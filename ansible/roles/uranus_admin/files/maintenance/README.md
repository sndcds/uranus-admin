# Kulturbytes Admin Maintenance Animation — Self-hosted Lottie

This directory contains the **self-hosted maintenance-mode animation** used by the
Kulturbytes Admin Ansible deployment. It is intentionally dependency-light, CSP-friendly,
works without third-party network requests and supports `prefers-reduced-motion`.

Related deployment documentation:
[Kulturbytes Admin Ansible](../../../README.md).

## Assets and licensing

`maintenance.json` is an original shape-only Lottie animation created for this
repository: a stationary server with three slowly orbiting update packets (6 seconds,
30 fps, 128 × 128). No images, fonts, expressions or external asset references.
It and `maintenance.js` use the project's AGPL-3.0 license; no third-party artwork.

`lottie.min.js` is the unmodified **lottie-web 5.13.0 Light (SVG)** player:

- Source: <https://github.com/airbnb/lottie-web/blob/v5.13.0/build/player/lottie_light.min.js>
- License: MIT, Copyright (c) 2015 Bodymovin; full notice in `LICENSE.lottie-web.txt`.
- SHA256: `9588432bec30c8ef8200bac4a67d8aaad881047bc2a6c9fa624d90ec96402410`
- 168,394 bytes uncompressed. Light omits expression evaluation; no `unsafe-eval`.

MIT permits redistribution and combination with this AGPL-3.0 project when its
copyright/permission notice is retained. Ansible installs that notice with the
runtime. The version and hash are pinned in tests; changes require source/license
review. Downloads happened only when vendoring, never during deployment or page use.

The initializer requests only `/__maintenance_assets/maintenance.json` from the same
origin. This is why the maintenance CSP uses `connect-src 'self'`; every external
connection remains forbidden. Reduced-motion visitors do not start the animation;
a later preference change pauses it. All information remains in the static HTML.
