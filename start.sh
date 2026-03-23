#!/bin/bash
# NeonTrade AI - Start Script
# Launches both backend (API) and frontend (Web UI)

echo "╔══════════════════════════════════════════╗"
echo "║     NeonTrade AI - Starting Up...        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Start backend
echo "[1/2] Starting backend server (port 8000)..."
cd "$(dirname "$0")/backend"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "      Backend PID: $BACKEND_PID"

# Wait for backend to be ready
sleep 3

# Start frontend
echo "[2/2] Starting frontend (Expo Web)..."
cd "$(dirname "$0")/frontend"
npx expo start --web --port 8081 &
FRONTEND_PID=$!
echo "      Frontend PID: $FRONTEND_PID"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  Backend API:  http://localhost:8000     ║"
echo "║  Frontend UI:  http://localhost:8081     ║"
echo "║  API Docs:     http://localhost:8000/docs║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Press Ctrl+C to stop both servers."

# Handle Ctrl+C - kill both processes
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

# Wait for either process to exit
wait
