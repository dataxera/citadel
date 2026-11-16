#!/bin/bash

# Start Uvicorn
echo "Starting Uvicorn..."
uv run uvicorn citadel.app:app --host 0.0.0.0 --port 8000 &

# Start Nginx
echo "Starting Nginx..."
nginx -g "daemon off;"
