# Architecture & Technical Documentation

## System Overview

```
┌─────────────────────────────────────────────────────┐
│                  React Frontend                      │
│   IntroScreen / Tutorial / SearchBar / SettingsPanel  │
│              SimilarityGraph (D3.js)                 │
└────────────────────┬────────────────────────────────┘
                     │
                     │ HTTP/REST
                     │
┌────────────────────▼────────────────────────────────┐
│              Flask Backend (Python)                  │
│  Feature extraction · similarity · overview layout    │
└────────────────────┬────────────────────────────────┘
                     │
        ┌────────────┴────────────┬────────────┐
        │                         │            │
        ▼                         ▼            ▼
   ┌─────────┐         ┌─────────────────┐ ┌──────────┐
   │ PokéAPI │         │ Local Cache     │ │ Audio    │
   │         │         │ (feature       │ │ Files    │
   │         │         │  vectors)       │ │ (.ogg)   │
   └─────────┘         └─────────────────┘ └──────────┘
```

## Backend Architecture

### `pokeapi_client.py` — PokéAPI access with caching

- `fetch_resource()`: core call with local JSON caching + retry
- `get_pokemon_data()` / `get_pokemon_species()`: Pokémon + species metadata (generation, habitat, flavor text)
- `download_cry()` / `get_cry_url()`: cry audio download
- `get_pokemon_by_generation()`: species list per generation

Cache location: `backend/data/cache/{endpoint}_{identifier}.json`.

### `audio_processor.py` — perceptual feature extraction

`extract_audio_features()` builds one feature vector per cry from several independently L2-normalized groups, concatenated with hand-tuned weights:

| Group | Signal | Weight |
|---|---|---|
| `mfcc` | 16-coefficient MFCC + delta, quantile stats | 1.25 |
| `texture` | spectral contrast, centroid, bandwidth, rolloff, flatness, ZCR, spectral entropy | 2.05 |
| `pitch` | chroma + tonnetz (tonal center) | 0.9 |
| `pitch_contour` | YIN f0 stats (voiced ratio, log-f0 mean/std/percentiles) | 0.75 |
| `envelope` | RMS, onset strength, cumulative-energy landmarks | 1.15 |
| `duration` | log-duration, raw duration | 0.12 |
| `axis` | 10 derived descriptors (pitch height/stability, tonality, noisiness, brightness, attack, sustain, modulation, sparkle, duration) used for overview layout, not similarity | — |
| `shape` | pitch-tolerant frequency-band autocorrelation "gesture" fingerprint | 2.35 |

`FEATURE_VERSION` is bumped whenever this layout changes; `manage.py build --force` clears cached vectors so they get recomputed.

### `similarity.py` — similarity scoring, clustering, and 2D layout

- `compute_cosine_similarity()`: when both vectors carry the full feature layout, similarity is a **weighted blend of per-block cosine scores** (shape 0.44, MFCC 0.19, texture 0.16, pitch contour 0.10, envelope 0.08, pitch 0.03) rather than one flat cosine over the whole vector. Falls back to plain cosine for other vector shapes (e.g. CLAP embeddings).
- `compute_pairwise_similarities()`: all-pairs similarity dict, `normalize_similarity()` maps `[-1, 1] → [0, 1]`.
- `compute_overview_layout()`: the most involved piece — turns the similarity graph into 2D coordinates plus a cluster assignment for the overview graph:
  1. Build a sparse per-node affinity graph (top-N neighbors, adaptively rescaled) and a dense raw-similarity matrix.
  2. Cluster: HDBSCAN over a UMAP embedding for neural (CLAP) vectors; agglomerative clustering over ranked acoustic descriptors for DSP vectors; spectral clustering as a fallback. Oversized clusters get locally re-split; tiny ones get merged into their nearest neighbor's cluster.
  3. `MUST_LINK_GROUPS` hard-codes a few ear-verified families (e.g. the squeaky/chirpy cluster, Gastly/Drowzee/Hypno) so clustering noise can't split them apart.
  4. Each cluster gets a local 2D embedding (spectral embedding or PCA fallback), then clusters are packed against each other with collision resolution so islands don't overlap, spaced closer when their cross-cluster similarity is high.
  5. For DSP vectors, final coordinates blend a "meaning-bearing" axis projection (buzz↔chirp, sustained↔punchy, built from the `axis` descriptor group) with the cluster-packed positions, so the overview's x/y actually correlates with audible qualities.
  6. Also computes `representativeness` (how central a Pokémon is within its own final cluster) and a `cluster_representative_id`.
- `compute_distance()`: normalized similarity → visualization distance (used for the selected/radial view).

### `data_pipeline.py` — orchestration

- `download_and_process_cry()`: download (or reuse cached) audio → extract features → cache vector as `.npy`
- `build_similarity_matrix()`: runs the above across a list of Pokémon IDs, computes pairwise similarities, and computes the overview layout
- `save_similarity_data()` / `load_similarity_data()`: JSON (de)serialization, including numpy vector round-tripping

### `data_store.py` — lightweight persistence for the web server

A trimmed copy of the same save/load logic that deliberately avoids importing `librosa`/`scikit-learn`, so `app.py` can start and serve cached data without pulling in the heavy ML stack. `app.py` imports from here, not from `data_pipeline.py`, for its hot path.

### `neural_audio.py` — optional CLAP embedding pipeline

An alternative to hand-built DSP features: runs Pokémon cries through `laion/clap-htsat-unfused` (HuggingFace CLAP) to get learned audio embeddings, then reuses the same `compute_pairwise_similarities` / `compute_overview_layout` machinery. Requires `backend/requirements-neural.txt` (torch, transformers, umap-learn, hdbscan) and is invoked via `manage.py build-clap`.

### `app.py` — Flask API

Routes are registered twice, with and without an `/api` prefix (`/pokemon` and `/api/pokemon` both work).

```
GET  /api/health
GET  /api/pokemon?generation=&limit=
GET  /api/pokemon/<id>
GET  /api/similarity/<id>?top_k=&min_similarity=
GET  /api/similarity-matrix?generation=&min_similarity=&include_links=
GET  /api/generations
POST /api/admin/build-matrix   { generation, force }
```

Notable behavior:

- `similarity_data` is loaded once into memory on first request (`load_data()`), backed by `data_store.py`.
- `/api/similarity/<id>` calibrates raw similarity scores per-neighborhood with a z-score + sigmoid (`_calibrate_similarity_scores`) so tightly clustered cosine scores spread out into a more visually useful range before the `min_similarity` cutoff is applied.
- `/api/similarity-matrix` caps each node's `nearest_neighbors` list to 16, and computes a fresh overview layout on the fly when a `generation` filter is applied (since the cached layout is for the full dataset).
- CORS origins are configurable via the `CORS_ORIGINS` env var, defaulting to common local dev ports plus the deployed Render URL.

## Frontend Architecture

### `App.jsx` — top-level orchestration

Owns most application state: selected Pokémon, loaded graph data, generation/type exclusion filters (as `Set`s — empty means "no filter"), intro/tutorial visibility, and a details cache (`pokemonDetailsById`) fetched lazily on hover/selection.

Key behaviors:

- Loads the full similarity matrix once on mount (`min_similarity=0.15`, no per-generation filter) and clears any stale `localStorage` entries from an earlier caching scheme that's no longer used.
- When a Pokémon is selected, fetches up to 320 candidate neighbors (`/api/similarity/<id>`) so client-side filtering doesn't silently drop nodes as filters change.
- Enforces a `MAX_NODES` cap (400) on the overview: toggling a generation/type back on is blocked (with a tooltip in `SettingsPanel`) if it would exceed the cap.
- Never lets the currently selected Pokémon's own generation/type be excluded (`lockedGenerations` / `lockedTypes`).
- `visibleClusterNodes`: in overview mode, merges any cluster smaller than 3 nodes into its most-connected larger neighbor cluster (using both matrix links and each node's `nearest_neighbors`) purely for display, so the overview doesn't show tiny disconnected islands.
- Cry playback uses a single shared `<audio>` ref so a new cry interrupts any currently playing one; Pikachu (id 25) is special-cased to play its legacy cry.

### `SimilarityGraph.jsx` — D3 rendering (overview + selected)

The largest component; owns two distinct layout modes off the same node/link data:

- **Overview mode**: nodes are placed at their precomputed `overview_x`/`overview_y` (from `compute_overview_layout` on the backend), then locally repacked in JS to resolve collisions, with dotted-outline cluster hulls (`d3.polygonHull`) drawn around each cluster and colored by a conic gradient of member types. Hovering a hull shows a cluster summary tooltip (common types/generation/habitat, median size).
- **Selected mode**: the selected Pokémon is fixed at center; neighbors are placed radially, with distance driven by `compute_distance`-style similarity math (mixing absolute and within-neighborhood-relative dissimilarity) and a spiral offset to keep same-distance nodes from stacking. A `d3.forceSimulation` with radial/collision forces does the settling, followed by manual passes that push nodes outward to respect both their target ring distance and collision with previously placed nodes.
- Node radius encodes a coarse size class (Small/Medium/Large/Huge) derived from height/weight; node fill is a linear gradient between a Pokémon's one or two types (`typeColors.js`).
- Hover tooltips merge live node data with lazily-fetched `pokemonDetailsById` (habitat, description) via `onPokemonHover`.
- Click plays the cry (with a short delay to disambiguate from double-click); double-click re-centers the graph on that Pokémon (`onPokemonSelect`).
- Accepts `tutorialStep`/`tutorialSelectedStarter` to dim non-target nodes and add a highlight halo during the guided tutorial.

### `SearchBar.jsx`

Name-prefix-first fuzzy filter over the currently visible (filtered) nodes, capped at 8 results; resets when `resetKey` changes (e.g. switching between overview and a selected Pokémon).

### `SettingsPanel.jsx`

Checkbox lists for generation and type, driven entirely by props from `App.jsx` (excluded sets, locked sets, over-max sets). Shows a "Max N — hide another first" tooltip when toggling an item back on would exceed `MAX_NODES`.

### `IntroScreen.jsx` / `Tutorial.jsx`

`IntroScreen` offers "Start Exploring" or "Tutorial". `Tutorial` walks through: pick a Gen I starter from a Pokéball → learn hover/click interactions → double-click to open the focused similarity view → short explanation of what that view means. Internal step state is remapped to the 3 external steps `App.jsx`/`SimilarityGraph.jsx` care about (`toExternalStep`).

### `LoadingText.jsx`

Small shared "Loading…" indicator with an animated ellipsis, used wherever the app is waiting on the initial matrix or a per-Pokémon neighborhood fetch.

### `api/client.js`

Axios wrapper around all backend routes (`getPokemonList`, `getPokemonDetails`, `getSimilarPokemon`, `getSimilarityMatrix`, `getGenerations`, `buildSimilarityMatrix`). Base URL comes from `REACT_APP_API_URL`, normalized to always end in `/api`.

## Data Flow Example

**Initial load:**

```
App.jsx mounts
  → apiClient.getSimilarityMatrix(null, 0.15, false)
  → Backend loads similarity_data.json into memory (once)
  → Returns nodes with overview_x/y, cluster_id, nearest_neighbors
  → excludedGenerations defaults to "everything except Gen I"
  → IntroScreen shown
```

**User double-clicks Pikachu in the overview:**

```
SimilarityGraph → onPokemonSelect(25) → App: setSelectedPokemon(25)
  → apiClient.getSimilarPokemon(25, top_k=320, min_similarity=0)
  → Backend calibrates + sorts neighbor scores, returns them
  → SimilarityGraph switches to selected/radial layout mode
  → Node clicks now play cries; graph is D3 forceSimulation + manual ring placement
```

## Deployment

`render.yaml` deploys the Flask backend to Render as a Python web service (`gunicorn app:app --workers 1 --threads 2 --timeout 120`, `rootDir: backend`). The frontend is a separate static build (`REACT_APP_API_URL` pointed at the deployed backend).

## Caching Strategy

```
1. PokéAPI response cache    backend/data/cache/       permanent, manual clear
2. Downloaded cry audio      backend/data/cries/       .ogg, versioned by CRY_SOURCE_VERSION
3. Extracted feature vectors backend/data/vectors/     .npy, versioned by FEATURE_VERSION
4. Similarity matrix         backend/data/similarity_data.json   loaded into memory on first request
```

## Dependencies

### Backend

- `flask`, `flask-cors`, `gunicorn`: HTTP server
- `librosa`, `scipy`: audio feature extraction
- `numpy`, `scikit-learn`: similarity, clustering
- `requests`: PokéAPI calls
- Optional (`requirements-neural.txt`): `torch`, `transformers`, `umap-learn`, `hdbscan`

### Frontend

- `react`, `react-dom`, `react-scripts`
- `d3`
- `axios`
