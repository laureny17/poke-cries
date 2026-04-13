#!/bin/bash
# Development startup script

echo "🎵 Pokémon Cry Similarity Explorer - Development Setup"
echo "======================================================"

# Start backend
echo -e "\n📦 Starting backend server..."
cd backend
python app.py &
BACKEND_PID=$!

# Start frontend
echo -e "\n🎨 Starting frontend development server..."
cd ../frontend
npm start

# Cleanup on exit
trap "kill $BACKEND_PID" EXIT
