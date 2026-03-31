#!/bin/bash

# Healthcheck script for SeerrBridge Unified Container
# Ensure curl is available, otherwise default to a simple check

# If 8777 (Main App) is available, we are healthy
if curl -sSf http://localhost:8777/api/health > /dev/null; then
    exit 0
fi

# If 8778 (Setup App) is available, we are in setup mode, which is also a valid "healthy" container state
if curl -sSf http://localhost:8778/api/setup/status > /dev/null; then
    exit 0
fi

# Otherwise, we are unhealthy (neither app is fully started up yet)
exit 1
