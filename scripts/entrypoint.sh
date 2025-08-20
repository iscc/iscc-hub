#!/bin/sh
set -e

# Signal handling for graceful shutdown
trap 'echo "Shutting down..."; exit 0' TERM INT

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
    # Production: only run migrations
    echo "📦 Running database migrations..."
    python manage.py migrate --no-input
fi

echo ""
echo "🌐 Starting server..."
echo "========================================="

# If no command provided, use default based on environment
if [ $# -eq 0 ]; then
    if [ "$ENVIRONMENT" = "development" ]; then
        # Development: Use uvicorn with reload
        exec uvicorn iscc_hub.asgi:application \
            --host 0.0.0.0 \
            --port ${PORT:-8000} \
            --reload \
            --use-colors
    else
        # Production: Use gunicorn with uvicorn workers
        exec gunicorn iscc_hub.asgi:application \
            -k uvicorn.workers.UvicornWorker \
            --bind 0.0.0.0:${PORT:-8000} \
            --workers ${WORKERS:-4} \
            --worker-connections ${WORKER_CONNECTIONS:-1000} \
            --max-requests ${MAX_REQUESTS:-1000} \
            --max-requests-jitter ${MAX_REQUESTS_JITTER:-50} \
            --timeout ${TIMEOUT:-30} \
            --graceful-timeout ${GRACEFUL_TIMEOUT:-30} \
            --keep-alive ${KEEP_ALIVE:-5} \
            --access-logfile - \
            --error-logfile - \
            --log-level ${LOG_LEVEL:-info}
    fi
else
    # Execute provided command
    exec "$@"
fi
