# Pokémon Cry Atlas

A web app that explores which Pokémon sound alike, using audio signal processing and an interactive force-directed map.

## Features

- **Perceptual audio fingerprinting**: each cry is reduced to a feature vector combining MFCC timbre, spectral texture (contrast, flatness, brightness, noisiness), pitch/chroma, a pitch-tolerant time-shape autocorrelation fingerprint, and envelope/attack shape
- **Weighted cosine similarity**: pairwise similarity is a weighted blend across those feature groups rather than a single flat cosine score, tuned so shape and timbre dominate over raw pitch
- **Automatic clustering**: an overview layout groups Pokémon into visually distinct "islands" using spectral/agglomerative clustering (or HDBSCAN for neural embeddings), with hand-picked must-link groups for cries that are obviously alike by ear
- **Two graph modes**:
  - **Overview** — all Pokémon (up to 400 at once) laid out by cluster, with dotted cluster outlines you can hover for a summary (common types, generations, habitat, size)
  - **Selected** — double-click any Pokémon to re-center the graph on it, arranged radially by similarity to that Pokémon
- **Search bar** to jump straight to a Pokémon by name
- **Filter panel** to include/exclude by generation or type, with a live count and guardrails so the graph never exceeds the node cap
- **Cry playback**: click a Pokémon to hear its cry (Pikachu intentionally uses its legacy cry for comparison purposes)
- **Rich hover tooltips**: sprite, types, generation, size class, habitat, and Pokédex description
- **Guided tutorial**: pick a Gen I starter, learn the hover/click/double-click interactions, then see the focused similarity view explained
- **Optional neural embedding pipeline**: a CLAP-based audio embedding path (`backend/src/neural_audio.py`) as an alternative to the hand-built DSP features, for "vibe"-based clustering instead of acoustic-descriptor clustering

## Technical Stack

### Backend

- **Python / Flask** for the REST API
- **Librosa + SciPy** for audio feature extraction
- **NumPy / scikit-learn** for similarity, clustering, and layout computation
- Optional: **PyTorch + Transformers (CLAP)**, **UMAP**, **HDBSCAN** for the neural embedding pipeline
- **Requests** for PokéAPI integration, with local JSON caching (fair-use compliant)
- **Gunicorn** for production serving (deployed via `render.yaml`)

### Frontend

- **React 18** for UI
- **D3.js** for the force-directed / radial graph rendering
- **Axios** for API communication

## Project Structure

```
poke-cries/
├── backend/
│   ├── src/
│   │   ├── pokeapi_client.py      # PokéAPI wrapper with local caching
│   │   ├── audio_processor.py     # Perceptual feature extraction
│   │   ├── similarity.py          # Weighted similarity + overview clustering/layout
│   │   ├── data_pipeline.py       # Download → extract → similarity orchestration
│   │   ├── data_store.py          # Lightweight load/save for the cached similarity_data.json
│   │   └── neural_audio.py        # Optional CLAP embedding pipeline
│   ├── data/
│   │   ├── cries/                 # Downloaded audio files
│   │   ├── vectors/                # Cached feature vectors
│   │   ├── cache/                 # PokéAPI response cache
│   │   └── similarity_data.json   # Built similarity matrix (served to the frontend)
│   ├── app.py                     # Flask application
│   ├── requirements.txt
│   └── requirements-neural.txt    # Extra deps for the CLAP pipeline
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── SimilarityGraph.jsx   # D3 overview + selected graph
│   │   │   ├── SearchBar.jsx
│   │   │   ├── SettingsPanel.jsx     # Generation/type filters
│   │   │   ├── IntroScreen.jsx
│   │   │   ├── Tutorial.jsx
│   │   │   └── LoadingText.jsx
│   │   ├── api/client.js
│   │   ├── typeColors.js
│   │   ├── App.jsx
│   │   └── App.css
│   ├── package.json
│   └── .env.example
├── manage.py                      # CLI for building the similarity matrix
├── dev.sh                         # Starts backend + frontend together
└── render.yaml                    # Render deployment config
```

## Setup Instructions

### Backend Setup

1. **Install Python dependencies**:

   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. **Run the Flask server**:

   ```bash
   python app.py
   ```

   The API will be available at `http://localhost:8000`

3. **Build the similarity matrix** (first time):

   ```bash
   python manage.py build --generation 1
   ```

   This downloads cries, extracts features, and computes similarities. Takes a few minutes on first run. Omit `--generation` to build all 1025 Pokémon.

   For the optional neural embedding path instead:

   ```bash
   pip install -r backend/requirements-neural.txt
   python manage.py build-clap --generation 1
   ```

### Frontend Setup

1. **Install dependencies**:

   ```bash
   cd frontend
   npm install
   ```

2. **Create `.env`** (see `.env.example`):

   ```
   REACT_APP_API_URL=http://localhost:8000/api
   ```

3. **Start the development server**:

   ```bash
   npm start
   ```

   The app opens at `http://localhost:3000`

Or run both at once from the project root with `./dev.sh`.

## API Endpoints

All routes are available with or without the `/api` prefix.

### GET `/api/health`

Health check.

### GET `/api/pokemon`

List Pokémon, with optional `generation` and `limit` query params.

### GET `/api/pokemon/<id>`

Detailed info for one Pokémon (types, sprite, habitat, description, cry URLs).

### GET `/api/similarity/<id>`

Pokémon most similar to a given one. Params: `top_k`, `min_similarity`.

### GET `/api/similarity-matrix`

Full graph data for visualization: nodes (with overview layout position, cluster id, nearest neighbors) and links. Params: `generation`, `min_similarity`, `include_links`.

### GET `/api/generations`

Available generations and their Pokémon counts.

### POST `/api/admin/build-matrix`

Build/rebuild the similarity matrix (computationally expensive). Body: `{ "generation": int, "force": bool }`.

## Data Source

All Pokémon data, audio files, and sprites are sourced from [PokéAPI](https://pokeapi.co/).

## Fair Use

This project respects PokéAPI's fair use policy:

- Local caching of downloaded resources
- Reasonable request frequency
- Proper attribution
- Educational use

## License

All rights reserved. This code is shared publicly for portfolio/reference purposes; it is not licensed for reuse, redistribution, or modification without permission.
