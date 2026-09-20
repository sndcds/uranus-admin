# Disposable CI fixture only. Both image inputs and the signed apt archive are pinned.
# The second image supplies only bootstrap CA certificates, never PostgreSQL/PostGIS.
FROM ubuntu@sha256:496754492fb28b4d3049432f2ca787449331e23fb14f0dd3fffea86bf5a93eb4
COPY --from=postgis/postgis@sha256:44126d872ac91993766c341e369c539e8196614321765d36a6f1bab0419a5fa5 /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
ENV DEBIAN_FRONTEND=noninteractive
RUN printf 'Types: deb\nURIs: https://snapshot.ubuntu.com/ubuntu/20260915T000000Z\nSuites: noble noble-updates noble-security\nComponents: main universe\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n' > /etc/apt/sources.list.d/ubuntu.sources \
 && apt-get -o Acquire::Retries=1 -o Acquire::https::Timeout=30 update \
 && apt-get install -y --no-install-recommends postgresql-16=16.15-0ubuntu0.24.04.1 postgresql-client-16=16.15-0ubuntu0.24.04.1 postgresql-16-postgis-3=3.4.2+dfsg-1ubuntu3 postgresql-16-postgis-3-scripts=3.4.2+dfsg-1ubuntu3 \
 && rm -rf /var/lib/apt/lists/* /var/lib/postgresql/16/main
ENV PATH=/usr/lib/postgresql/16/bin:$PATH
COPY entrypoint.sh /usr/local/bin/console-test-entrypoint
RUN chmod 755 /usr/local/bin/console-test-entrypoint
USER postgres
ENV PGDATA=/var/lib/postgresql/console_test
HEALTHCHECK --interval=2s --timeout=3s --retries=30 CMD pg_isready -h 127.0.0.1 -U postgres -d uranus_ansible_test
ENTRYPOINT ["/usr/local/bin/console-test-entrypoint"]
