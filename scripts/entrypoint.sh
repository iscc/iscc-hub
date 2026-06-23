#!/bin/sh
set -e

# Determine environment from ENV variable (defaults to production)
ENVIRONMENT=${ENVIRONMENT:-production}

echo "========================================="
echo "ISCC-HUB - Environment: ${ENVIRONMENT}"
echo "========================================="

# Ensure data directory exists
mkdir -p /app/data

# Initialize database
if [ "$ENVIRONMENT" = "development" ]; then
    echo "🔧 Initializing development database..."
    poe init
else
    # Production: ensure migrations exist and apply them
    echo "📦 Ensuring database migrations exist..."

    # Check if migrations directory exists and has migration files
    if [ ! -d "iscc_hub/migrations" ] || [ -z "$(find iscc_hub/migrations -name '0001_*.py' 2>/dev/null)" ]; then
        echo "  Creating initial migrations..."
        python manage.py makemigrations iscc_hub --no-input
    fi

    echo "  Applying database migrations..."
    python manage.py migrate --no-input

    # Ensure the admin superuser exists when a password is configured. Idempotent: skips when the
    # user already exists (durable volume) and recreates it on a clean DB. Non-fatal so a bootstrap
    # hiccup never blocks startup. Replaces the superuser side effect of the removed deploy-time
    # `db_management.py reset`.
    if [ -n "${ISCC_HUB_ADMIN_PWD:-}" ]; then
        echo "  Ensuring admin superuser exists..."
        if ! python scripts/db_management.py create-superuser; then
            echo "  Admin superuser bootstrap failed; continuing."
        fi
    fi

    # Perform initial hub sync if enabled. Non-fatal under `set -e`: hub-list sync is not
    # load-bearing and the periodic loop is the retry path.
    if [ "${ISCC_HUB_LIST_INITIAL_SYNC:-true}" = "true" ]; then
        echo "  Syncing hub list from GitHub..."
        if ! python manage.py sync_hubs --quiet; then
            echo "  Hub list sync failed; continuing, periodic sync will retry."
        fi
    fi
fi

# If a custom command is provided, run it directly (no server, no scheduler loops).
if [ $# -ne 0 ]; then
    exec "$@"
fi

echo ""
echo "🌐 Starting server..."
echo "========================================="

# Background periodic jobs (replaces the Django-Q cluster). Each loop is independent and
# idempotent; interval 0 disables it. The checkpoint also rebuilds lazily on read, so a
# missed refresh self-heals — these loops are a freshness optimization, not correctness.

# Resolve a scheduler interval to a non-negative integer of seconds (0 disables). A
# non-integer value (e.g. a typo like "24h") falls back to the documented default with a
# loud warning, so a misconfigured interval is never silently dropped. The warning goes to
# stderr; only the resolved number reaches stdout for the command substitution below.
resolve_interval() {
    case "$1" in
        ''|*[!0-9]*)
            echo "  WARNING: $3='$1' is not a non-negative integer of seconds; using default $2." >&2
            echo "$2"
            ;;
        *) echo "$1" ;;
    esac
}

HUB_SYNC_INTERVAL=$(resolve_interval "${ISCC_HUB_HUB_SYNC_INTERVAL:-3600}" 3600 ISCC_HUB_HUB_SYNC_INTERVAL)
CHECKPOINT_INTERVAL=$(resolve_interval "${ISCC_HUB_CHECKPOINT_INTERVAL:-86400}" 86400 ISCC_HUB_CHECKPOINT_INTERVAL)
SCHEDULER_PIDS=""

cleanup_children() {
    echo "Shutting down..."
    if [ -n "$SCHEDULER_PIDS" ]; then
        kill $SCHEDULER_PIDS 2>/dev/null || true
    fi
    if [ -n "${SERVER_PID:-}" ]; then
        # TERM the server and wait for *it* (not the scheduler loops) to drain in-flight
        # requests. Waiting on the specific PID — rather than a bare `wait` — means a
        # scheduler loop that somehow escaped the kill above can never hang shutdown.
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}

# Keep the shell as PID 1 so this trap can stop the scheduler loops and the server on shutdown.
trap 'cleanup_children; exit 0' TERM INT

# `|| true` keeps a transient failure (e.g. a GitHub blip on hub-sync) from killing a loop.
# `sleep`-first means the boot case is already covered by the startup sync above, so each loop
# begins one interval later. Defaults: hub-sync hourly; checkpoint daily.
if [ "$HUB_SYNC_INTERVAL" -gt 0 ]; then
    ( while sleep "$HUB_SYNC_INTERVAL"; do python manage.py sync_hubs --quiet || true; done ) &
    SCHEDULER_PIDS="$SCHEDULER_PIDS $!"
fi
if [ "$CHECKPOINT_INTERVAL" -gt 0 ]; then
    ( while sleep "$CHECKPOINT_INTERVAL"; do python manage.py refresh_checkpoint || true; done ) &
    SCHEDULER_PIDS="$SCHEDULER_PIDS $!"
fi

# Start gunicorn as a child process and wait on it (instead of `exec`-replacing the shell).
if [ "$ENVIRONMENT" = "development" ]; then
    # Development: Use gunicorn with reload
    gunicorn iscc_hub.wsgi:application \
        --bind 0.0.0.0:${PORT:-8000} \
        --workers 1 \
        --reload \
        --access-logfile - \
        --error-logfile - \
        --log-level info &
else
    # Production: Use gunicorn with sync workers (WSGI)
    gunicorn iscc_hub.wsgi:application \
        --bind 0.0.0.0:${PORT:-8000} \
        --workers ${WORKERS:-4} \
        --threads ${THREADS:-1} \
        --max-requests ${MAX_REQUESTS:-1000} \
        --max-requests-jitter ${MAX_REQUESTS_JITTER:-50} \
        --timeout ${TIMEOUT:-30} \
        --graceful-timeout ${GRACEFUL_TIMEOUT:-30} \
        --keep-alive ${KEEP_ALIVE:-5} \
        --access-logfile - \
        --error-logfile - \
        --log-level ${LOG_LEVEL:-info} &
fi
SERVER_PID=$!

# Wait for the server. On a TERM/INT signal the trap runs cleanup_children and exits. On the
# server exiting by itself, `|| SERVER_STATUS=$?` captures its code without tripping `set -e`.
SERVER_STATUS=0
wait "$SERVER_PID" || SERVER_STATUS=$?
cleanup_children
exit "$SERVER_STATUS"
