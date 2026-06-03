#!/bin/bash
# Start the Temporal worker, the FastAPI server, and (optionally) the Gmail inbox poller.

echo "Starting JobHunt worker..."

# Start Temporal worker in background
python worker.py &
WORKER_PID=$!
echo "Started Temporal worker (PID: $WORKER_PID)"

# Optionally start the Gmail inbox poller. It requires Gmail OAuth to be configured,
# so it is opt-in: set RUN_EMAIL_POLLER=true to enable. When running, it signals the
# follow-up workflow on reply (ENABLE_TEMPORAL_SIGNALS); the workflow's durable DB
# re-check after every timer is the always-on backstop regardless.
POLLER_PID=""
if [ "${RUN_EMAIL_POLLER:-false}" = "true" ]; then
    python email_poller.py &
    POLLER_PID=$!
    echo "Started Gmail inbox poller (PID: $POLLER_PID)"
fi

# Start FastAPI server in background
python -m uvicorn main:app --host 0.0.0.0 --port 8080 &
UVICORN_PID=$!
echo "Started FastAPI server (PID: $UVICORN_PID)"

# Wait for the core processes (and the poller if it was started)
PIDS="$WORKER_PID $UVICORN_PID"
[ -n "$POLLER_PID" ] && PIDS="$PIDS $POLLER_PID"
wait $PIDS
