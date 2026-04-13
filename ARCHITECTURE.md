# Architecture & Technical Documentation

## System Overview

The Pokémon Cry Similarity Explorer is a full-stack application that processes audio files and visualizes relationships through a web interface.

```
┌─────────────────────────────────────────────────────┐
│                  React Frontend                      │
│              (D3.js Visualization)                   │
└────────────────────┬────────────────────────────────┘
                     │
                     │ HTTP/REST
                     │
┌────────────────────▼────────────────────────────────┐
│              Flask Backend (Python)                  │
│         (Audio Processing & Analysis)               │
└────────────────────┬────────────────────────────────┘
                     │
        ┌────────────┴────────────┬────────────┐
        │                         │            │
        ▼                         ▼            ▼
   ┌─────────┐         ┌─────────────────┐ ┌──────────┐
   │ PokéAPI │         │ Local Cache     │ │ Audio    │
   │         │         │ (MFCC Vectors) │ │ Files    │
   └─────────┘         └─────────────────┘ └──────────┘
```

## Backend Architecture

### Module: `pokeapi_client.py`

**Purpose**: Interface with PokéAPI with local caching

**Key Functions**:

- `fetch_resource()`: Core function for API calls with caching
- `get_pokemon_data()`: Fetch Pokémon details (sprites, cries, types, etc.)
- `get_pokemon_species()`: Fetch species data (generation, egg groups, etc.)
- `download_cry()`: Download audio file from URL
- `get_cry_url()`: Get the URL for a Pokémon's cry

**Caching Strategy**:

```
Cache Directory: backend/data/cache/
Files: {endpoint}_{identifier}.json

Example:
  pokemon_1.json -> Full Pokémon data for ID 1
  pokemon-species_1.json -> Species info for ID 1
```

### Module: `audio_processor.py`

**Purpose**: Extract audio features using Mel Frequency Cepstral Coefficients

**Key Functions**:

- `load_and_preprocess_audio()`: Load audio, apply preprocessing
- `extract_mfcc_vector()`: Get fixed-size feature vector from audio
- `extract_mfcc_features()`: Get raw MFCC spectrograms

**MFCC Details**:

```
Process:
1. Load audio file (OGG format from PokéAPI)
2. Resample to 22050 Hz
3. Calculate MFCC curves over time (13 coefficients)
4. Compute statistics: mean + standard deviation
5. Final vector: 26 features (13 means + 13 stds)

Output: 1D array of 26 floating-point numbers
```

### Module: `similarity.py`

**Purpose**: Compute similarity metrics between feature vectors

**Key Functions**:

- `compute_cosine_similarity()`: Calculate cos(θ) between two vectors
- `compute_pairwise_similarities()`: Build complete similarity matrix
- `get_similar_pokemon()`: Find K most similar Pokémon
- `normalize_similarity()`: Convert [-1, 1] → [0, 1] range
- `compute_distance()`: Convert similarity to visualization distance

**Similarity Scoring**:

```
Cosine Similarity: cos(θ) = (A · B) / (|A| |B|)

Range: [-1.0, 1.0]
- 1.0 = identical sound
- 0.0 = orthogonal (no similarity)
- -1.0 = opposite sound (rare)

Normalized: (score + 1) / 2 → [0, 1]
- 0.0 = completely different
- 1.0 = identical
```

### Module: `data_pipeline.py`

**Purpose**: Orchestrate the complete workflow

**Key Functions**:

- `build_similarity_matrix()`: Main processing pipeline
- `download_and_process_cry()`: Download + extract features for one Pokémon
- `get_generation_pokemon()`: Get all Pokémon from a generation
- `save_similarity_data()`: Serialize data to JSON

**Pipeline Flow**:

```
1. For each Pokémon ID:
   a. Get cry URL from PokéAPI
   b. Download audio file (or use cache)
   c. Extract MFCC features
   d. Cache the feature vector

2. Compute pairwise similarities
   - Between all Pokémon pairs
   - Result: Dictionary of (id1, id2) → score

3. Save to disk for frontend
   - Vectors serialized as lists
   - Similarities as key-value pairs
```

### Module: `app.py` (Flask API)

**Purpose**: REST API endpoints for frontend communication

**API Endpoints**:

```
GET /api/health
  Response: {"status": "ok"}

GET /api/pokemon?generation=1&limit=100
  Response: Array of Pokémon with metadata

GET /api/pokemon/<id>
  Response: Single Pokémon detail

GET /api/similarity/<id>?top_k=20&min_similarity=0.5
  Response: Array of similar Pokémon

GET /api/similarity-matrix?generation=1&min_similarity=0.3
  Response: {nodes: [...], links: [...]} for D3.js

POST /api/admin/build-matrix
  Body: {"generation": 1, "force": false}
  Response: Build status

GET /api/generations
  Response: Available generation metadata
```

**Data Loading**:

```python
# On startup
GET /api/similarity-matrix
  ↓
  Check if data cached
  ↓
  Load similarity_data.json
  ↓
  Cache in memory
```

## Frontend Architecture

### Component: `App.jsx` (Main)

**State**:

```
- generation: Int | null (current generation filter)
- selectedPokemon: Int | null (clicked Pokémon)
- similarPokemon: Array (top similar to selected)
- graphData: {nodes: [...], links: [...]}
- minSimilarity: Float (0.0 - 1.0)
```

**Effects**:

1. When generation changes → fetch similarity matrix
2. When selectedPokemon changes → fetch similar Pokémon

### Component: `SimilarityGraph.jsx` (D3.js)

**Visualization**:

```
Force Simulation:
├── Link Force: Based on similarity distance
├── Charge Force: Repel nodes
├── Center Force: Keep graph centered
└── Collision Force: Prevent overlap

Nodes:
├── Position: Computed by D3 simulation
├── Size: 40px diameter
├── Image: Pokémon sprite
└── Color: Selected/highlighted state

Links:
├── Thickness: Based on similarity
├── Opacity: Based on similarity
└── Highlighted: If adjacent to selected
```

**Interactions**:

- **Click node**: Select Pokémon, update sidebar
- **Drag node**: Temporary node fixing (released on mouseup)
- **Zoom**: Mouse wheel / trackpad pinch
- **Pan**: Click and drag background

### Component: `GenerationFilter.jsx`

**Function**: Dropdown to select generation or view all

**Data Flow**:

```
Dropdown → onChange → setGeneration
        → useEffect → apiClient.getSimilarityMatrix()
        → Update graphData
```

### Component: `PokemonSelector.jsx` (Sidebar)

**Layout**:

```
┌─────────────────────┐
│  Selected Pokémon   │
│  [Image + Stats]    │
├─────────────────────┤
│ Similar Pokémon     │
│ [Ranked List]       │
├─────────────────────┤
│ All Pokémon         │
│ [Searchable List]   │
└─────────────────────┘
```

### Module: `api/client.js`

**Purpose**: HTTP client for all API calls

**Methods**:

```javascript
apiClient.getPokemonList(generation, limit);
apiClient.getSimilarPokemon(id, topK, minSimilarity);
apiClient.getSimilarityMatrix(generation, minSimilarity);
apiClient.getGenerations();
```

## Data Flow Example

**User selects Generation 1:**

```
Frontend (App.jsx)
  ↓ setGeneration(1)
  ↓ useEffect triggers
  ↓ apiClient.getSimilarityMatrix(1, 0.3)
  ↓
Backend (app.py)
  ↓ GET /api/similarity-matrix?generation=1&min_similarity=0.3
  ↓ Load from cache or memory
  ↓ Filter nodes by generation
  ↓ Build links above threshold
  ↓ Return JSON
  ↓
Frontend (SimilarityGraph.jsx)
  ↓ D3 creates force simulation
  ↓ Renders 151 Pokémon nodes
  ↓ Draws ~500 links
  ↓ Displays in viewport
```

**User clicks on Pikachu:**

```
Frontend (Node clicked)
  ↓ onPokemonSelect(25)
  ↓ setSelectedPokemon(25)
  ↓ useEffect triggers
  ↓ apiClient.getSimilarPokemon(25, 20, 0.0)
  ↓
Backend (app.py)
  ↓ GET /api/similarity/<25>?top_k=20&min_similarity=0.0
  ↓ Look up similarities[(25, x)] for all x
  ↓ Sort by score descending
  ↓ Return top 20 with details
  ↓
Frontend (PokemonSelector.jsx)
  ↓ Render similar Pokémon list
  ↓ Highlight connections in graph
  ↓ Show details in sidebar
```

## Performance Characteristics

### Backend

- **First build**: 2-5 minutes per generation
  - Download ~150 audio files
  - Extract MFCC for each (0.5-1s per file)
  - Compute similarity matrix (O(n²))

- **Subsequent requests**: <500ms
  - Loaded entirely into memory
  - Matrix operations cached

### Frontend

- **Graph rendering**: ~2s for 1000 nodes
- **Interaction response**: <100ms (D3 is fast)
- **Data transfer**: ~5MB for full matrix

## Caching Strategy

**Cache Levels**:

```
1. API Response Cache
   Location: backend/data/cache/
   Lifetime: Permanent (manual clear needed)

2. Audio Files
   Location: backend/data/cries/
   Format: .ogg (from PokéAPI)

3. Feature Vectors
   Location: backend/data/vectors/
   Format: .npy (NumPy binary)

4. Similarity Matrix
   Location: backend/data/similarity_data.json
   Loaded into memory on startup
```

## Dependencies

### Backend

- **flask**: HTTP server
- **librosa**: Audio feature extraction
- **numpy**: Numerical computing
- **scikit-learn**: Cosine similarity
- **requests**: API calls

### Frontend

- **react**: UI framework
- **d3**: Graph visualization
- **axios**: HTTP client

## Testing Recommendations

1. **Unit tests** for MFCC extraction
2. **Integration tests** for API endpoints
3. **Visual tests** for D3 interactions
4. **Performance tests** for large graphs

## Future Optimization Ideas

- **Dimensionality reduction**: Use t-SNE for 2D positions
- **Streaming data**: Lazy-load Pokémon data
- **Worker threads**: Process audio in background
- **GraphQL**: Replace REST API
- **WebGL rendering**: For millions of nodes
