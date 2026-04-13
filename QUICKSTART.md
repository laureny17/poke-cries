# Quick Start Guide

## Prerequisites

- Python 3.8+
- Node.js 16+ and npm
- Internet connection (for PokéAPI access)

## Installation & Running

### Option 1: Using Development Script (macOS/Linux)

```bash
# Make script executable
chmod +x dev.sh

# Start both backend and frontend
./dev.sh
```

### Option 2: Manual Setup

**Terminal 1 - Backend:**

```bash
cd backend
pip install -r requirements.txt
python app.py
```

**Terminal 2 - Frontend:**

```bash
cd frontend
npm install
npm start
```

### Option 3: Using Management Script (Recommended for data building)

```bash
# Build similarity matrix for Generation 1
python manage.py build --generation 1

# Build for all generations
python manage.py build

# Force rebuild
python manage.py build --force
```

## First Time Setup

1. **Install dependencies** (backend)

   ```bash
   cd backend && pip install -r requirements.txt
   ```

2. **Build similarity matrix** (takes a few minutes on first run)

   ```bash
   cd backend
   python app.py  # Start server in one terminal

   # In another terminal
   curl -X POST http://localhost:8000/api/admin/build-matrix \
     -H "Content-Type: application/json" \
     -d '{"generation": 1}'
   ```

3. **Start frontend** (in separate terminal)

   ```bash
   cd frontend
   npm install
   npm start
   ```

4. **Open browser** to `http://localhost:3000`

## What Each Part Does

### Backend (`/backend`)

- **`app.py`**: Flask server with API endpoints
- **`src/pokeapi_client.py`**: Fetches Pokémon data with local caching
- **`src/audio_processor.py`**: Extracts MFCC features from audio
- **`src/similarity.py`**: Computes cosine similarity between cries
- **`src/data_pipeline.py`**: Orchestrates the full data processing

### Frontend (`/frontend`)

- **`src/App.jsx`**: Main application component
- **`src/components/SimilarityGraph.jsx`**: D3.js network visualization
- **`src/components/GenerationFilter.jsx`**: Generation selector
- **`src/components/PokemonSelector.jsx`**: Pokémon list and details
- **`src/api/client.js`**: API communication

## Common Tasks

### Build matrix for specific generation

```bash
python manage.py build --generation 3
```

### Rebuild everything

```bash
python manage.py build --force
```

### View backend API health

```bash
curl http://localhost:8000/api/health
```

### View available generations

```bash
curl http://localhost:8000/api/generations
```

## Troubleshooting

**Port already in use?**

- Backend (8000): `lsof -i :8000` and kill the process
- Frontend (3000): `lsof -i :3000` and kill the process

**CORS errors?**

- Make sure backend is running with CORS enabled (it is by default)

**No audio playing?**

- Click a Pokémon to select it
- The app loads audio URLs but doesn't auto-play

**Matrix build taking forever?**

- Normal on first build (~1-2 min per generation)
- Subsequent runs use cache from `/backend/data/` folder

## Performance Tips

- Start with a single generation for testing
- Adjust "Minimum Similarity" slider to reduce graph connections
- Zoom/pan in the graph to explore specific areas

## Environment Variables

Create `frontend/.env`:

```
REACT_APP_API_URL=http://localhost:8000/api
```

Create `backend/.env` (optional):

```
FLASK_ENV=development
FLASK_DEBUG=true
```

---

Enjoy exploring Pokémon cry similarities! 🎵🔊
