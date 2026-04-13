# Pokémon Cry Similarity Explorer

A web application to discover which Pokémon sound alike using audio signal processing and interactive visualization.

## Features

- **Audio Analysis**: Extracts Mel Frequency Cepstral Coefficients (MFCCs) from Pokémon cries
- **Similarity Scoring**: Computes cosine similarity between all Pokémon cries
- **Interactive Map**: D3.js force-directed graph visualization showing Pokémon as nodes
- **Generation Filtering**: View Pokémon from specific generations
- **Pokémon Selection**: Click on any Pokémon to see its most similar neighbors
- **Similarity Threshold**: Adjust the minimum similarity to filter connections

## Technical Stack

### Backend

- **Python** with Flask for API
- **Librosa** for audio processing and MFCC extraction
- **scikit-learn** for cosine similarity calculations
- **Requests** for PokéAPI integration
- **Caching** system for local data storage (fair use compliant)

### Frontend

- **React 18** for UI components
- **D3.js** for force-directed graph visualization
- **Axios** for API communication
- **CSS3** for styling and responsive design

## Project Structure

```
poke-cries/
├── backend/
│   ├── src/
│   │   ├── __init__.py
│   │   ├── pokeapi_client.py      # PokéAPI wrapper with caching
│   │   ├── audio_processor.py     # MFCC extraction
│   │   ├── similarity.py          # Cosine similarity calculations
│   │   └── data_pipeline.py       # Data processing orchestration
│   ├── data/
│   │   ├── cries/                 # Downloaded audio files
│   │   ├── vectors/               # Cached MFCC vectors
│   │   └── cache/                 # API response cache
│   ├── app.py                     # Flask application
│   └── requirements.txt
├── frontend/
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── components/
│   │   │   ├── SimilarityGraph.jsx
│   │   │   ├── GenerationFilter.jsx
│   │   │   └── PokemonSelector.jsx
│   │   ├── api/
│   │   │   └── client.js
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── index.js
│   │   └── index.css
│   ├── package.json
│   └── .env.example
└── README.md
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

3. **Build similarity matrix** (first time):

   ```bash
   curl -X POST http://localhost:8000/api/admin/build-matrix \
     -H "Content-Type: application/json" \
     -d '{"generation": 1}'
   ```

   This downloads cries, extracts features, and computes similarities. Takes time on first run!

### Frontend Setup

1. **Install dependencies**:

   ```bash
   cd frontend
   npm install
   ```

2. **Create .env file**:

   ```
   REACT_APP_API_URL=http://localhost:8000/api
   ```

3. **Start development server**:

   ```bash
   npm start
   ```

   The app will open at `http://localhost:3000`

## API Endpoints

### GET `/api/health`

Health check.

### GET `/api/pokemon`

Get list of Pokémon.

- Query params: `generation`, `limit`

### GET `/api/pokemon/<id>`

Get specific Pokémon info.

### GET `/api/similarity/<id>`

Get Pokémon most similar to given ID.

- Query params: `top_k`, `min_similarity`

### GET `/api/similarity-matrix`

Get full similarity matrix for visualization.

- Query params: `generation`, `min_similarity`

### GET `/api/generations`

Get list of available generations.

### POST `/api/admin/build-matrix`

Build/rebuild similarity matrix (computationally expensive).

- Body: `{ "generation": int, "force": bool }`

## How It Works

1. **Audio Extraction**: Download Pokémon cries from PokéAPI
2. **Feature Extraction**: Use Librosa to extract 13 MFCC coefficients from each cry
3. **Vector Normalization**: Compute mean and std of MFCCs to create fixed-size vectors
4. **Similarity Calculation**: Use cosine similarity to compare all pairs
5. **Visualization**: Render as force-directed graph where:
   - **Node size**: Represents Pokémon
   - **Node color**: Changes on selection
   - **Link strength/distance**: Based on similarity score
   - **Zoom/pan**: Available for exploration

## Cool Finds to Explore

- **Bird Pokémon**: See if they cluster together (chirping sounds)
- **Electric-types**: Look for common "electric" characteristics
- **Generation differences**: Compare Gen 1 vs newer gens (sound quality evolution)
- **Evolution families**: Check if evolutions sound similar to pre-evolutions

## Future Enhancements

- [ ] Play audio on hover/click
- [ ] Category-based coloring (by type, generation, etc.)
- [ ] Search by name/ID
- [ ] Export graph as image
- [ ] Customizable similarity metrics
- [ ] Shared links for specific visualizations
- [ ] Mobile-friendly responsive design

## Data Source

All Pokémon data, audio files, and sprites sourced from [PokéAPI](https://pokeapi.co/).

## Fair Use

This project respects PokéAPI's fair use policy:

- ✅ Local caching of downloaded resources
- ✅ Reasonable request frequency
- ✅ Proper attribution
- ✅ Educational use

## License

MIT License - feel free to use and modify!

---

**Note**: The initial similarity matrix build takes time depending on your internet connection and computer specs. Subsequent requests use cached data.
