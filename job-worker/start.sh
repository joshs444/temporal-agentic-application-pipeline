#!/bin/bash
# Start both FastAPI server and Temporal worker

echo "Starting JobHunt worker..."

# Start Temporal worker in background
python worker.py &
WORKER_PID=$!
echo "Started Temporal worker (PID: $WORKER_PID)"

# Start FastAPI server in foreground
python -m uvicorn main:app --host 0.0.0.0 --port 8080 &
UVICORN_PID=$!
echo "Started FastAPI server (PID: $UVICORN_PID)"

# Wait for both processes
wait $WORKER_PID $UVICORN_PID
