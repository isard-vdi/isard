#!/usr/bin/env bash
# Wait until the IsardVDI apiv4 and socketio services are reachable inside
# the docker-compose network. Invoked by the integration:real CI job
# after `docker compose up -d`, before running pytest.
#
# Usage:
#   APIV4_URL=http://isard-apiv4:5000 \
#   SOCKETIO_URL=http://isard-socketio:5000 \
#   AUTH_URL=http://isard-authentication:1313 \
#   ./testing/integration/wait-for-stack.sh [max_seconds]

set -euo pipefail

MAX_WAIT="${1:-180}"
APIV4_URL="${APIV4_URL:-http://isard-apiv4:5000}"
SOCKETIO_URL="${SOCKETIO_URL:-http://isard-socketio:5000}"
AUTH_URL="${AUTH_URL:-http://isard-authentication:1313}"

probe() {
    # curl returns non-zero on HTTP ≥ 400 with -f; without -f we accept any
    # successful TCP connection so the listener just has to be bound. That
    # is sufficient for "stack ready" — the individual tests verify richer
    # behaviour themselves.
    curl -s -o /dev/null -m 3 "$1" > /dev/null 2>&1
}

started=$SECONDS
for target in "$APIV4_URL/api/v4/openapi.json" "$SOCKETIO_URL/socket.io/?EIO=4&transport=polling" "$AUTH_URL/authentication/check"; do
    while ! probe "$target"; do
        if (( SECONDS - started > MAX_WAIT )); then
            echo "wait-for-stack: timeout after ${MAX_WAIT}s waiting for $target" >&2
            exit 1
        fi
        sleep 2
    done
    echo "wait-for-stack: $target reachable"
done

echo "wait-for-stack: stack ready after $((SECONDS - started))s"
