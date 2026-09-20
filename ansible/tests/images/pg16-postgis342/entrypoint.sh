#!/bin/sh
# Disposable fixture with public, synthetic test credentials; never production.
set -eu
umask 077
if [ -e "$PGDATA" ]; then
    echo 'Refuse pre-existing fixture data directory' >&2
    exit 1
fi
password_file=$(mktemp)
printf '%s\n' 'local-fixture-only' > "$password_file"
initdb -D "$PGDATA" --username=postgres --pwfile="$password_file" \
    --auth-local=trust --auth-host=scram-sha-256
rm "$password_file"
printf '%s\n' 'host all all 0.0.0.0/0 scram-sha-256' >> "$PGDATA/pg_hba.conf"
pg_ctl -D "$PGDATA" -o "-c listen_addresses='' -c unix_socket_directories=/tmp" -w start
createdb -h /tmp -U postgres uranus_ansible_test
pg_ctl -D "$PGDATA" -m fast -w stop
exec postgres -D "$PGDATA" -c listen_addresses='*'
