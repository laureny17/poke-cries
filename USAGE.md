# Usage Guide & Examples

## Installation

### Prerequisites Check

```bash
# Check Python version
python3 --version  # Should be 3.8+

# Check Node.js version
node --version     # Should be 16+
npm --version      # Should be 8+
```

### Step 1: Backend Setup

```bash
# Navigate to project
cd /Users/lauren/classes/4.032/poke-cries

# Enter backend directory
cd backend

# Install Python dependencies
pip install -r requirements.txt

# Expected output:
# Successfully installed Flask==3.0.0 librosa==0.10.0 ...
```

### Step 2: Start Backend Server

```bash
# In backend/ directory
python app.py

# Expected output:
# * Serving Flask app 'app'
# * Running on http://127.0.0.1:8000
```

Backend is now ready at `http://localhost:8000`

### Step 3: Build Similarity Matrix (Optional - First Time)

```bash
# In a NEW terminal, from project root
python manage.py build --generation 1

# Or for all generations:
python manage.py build

# Expected output:
# 🔨 Building similarity matrix...
# 📊 Processing Generation 1 (151 Pokémon)
# Processing 151 Pokémon...
# ...✅ Successfully built similarity matrix!
```

This takes 2-5 minutes depending on internet speed.

### Step 4: Frontend Setup

```bash
# In a NEW terminal, from project root
cd frontend

# Install npm dependencies
npm install

# Expected output:
# added 200 packages in 30 seconds

# Start development server
npm start

# Expected output:
# Compiled successfully!
# On Your Network: http://192.168.0.100:3000
# Localhost: http://localhost:3000
```

Frontend opens automatically at `http://localhost:3000`

---

## Sample Usage Session

### Scenario 1: Explore Generation 1 Pokémon

1. **Open browser**: `http://localhost:3000`
2. **Wait for graph**: D3.js visualization loads (2-3 seconds)
3. **Select Generation**:
   - Click "Generation" dropdown
   - Choose "Generation 1 (151 Pokémon)"
4. **Graph updates** with all Gen 1 Pokémon
5. **Click on Pikachu**:
   - Node highlights
   - Sidebar shows: ID #25, Electric-type, height/weight
   - "Most Similar" section appears
6. **Explore similar Pokémon**:
   - See list ranked by similarity
   - Click another to center on it

### Scenario 2: Find Similar Pokémon

1. **Adjust minimum similarity slider**:
   - Default: 30%
   - Move to 50% to see more similar ones
   - Move to 0% to see all connections
2. **Click a Pokémon** (e.g., Bulbasaur)
3. **Sidebar shows similar Pokémon**:
   - Other grass/poison types likely nearby
   - Ranked by similarity percentage
4. **Click a similar one** to explore its neighbors

### Scenario 3: Compare Generations

1. **Select Generation 3** from dropdown
2. **Notice differences**:
   - Different 151 Pokémon
   - Different clustering patterns
   - Different sound qualities
3. **Switch back to Gen 1** to compare
4. **Hypothesis**: Gen 3 may have different audio quality

---

## CLI Usage

### Build Similarity Matrix

```bash
# For specific generation
python manage.py build --generation 1

# For all generations at once
python manage.py build

# Force rebuild (overwrite existing)
python manage.py build --force

# With specific generation and force
python manage.py build --generation 3 --force
```

### Output Examples

```
✓ Similarity data already exists at backend/data/similarity_data.json
Use --force to rebuild

🔨 Building similarity matrix...
📊 Processing Generation 1 (151 Pokémon)
Processing 151 Pokémon...
Progress: 0/151
Progress: 50/151
Progress: 100/151
Progress: 150/151
Successfully processed 151 Pokémon
Computing similarity matrix...
✅ Successfully built similarity matrix!
💾 Saved to: backend/data/similarity_data.json
📈 Pokémon processed: 151
```

---

## API Usage Examples

### With curl

```bash
# Health check
curl http://localhost:8000/api/health

# Get all Pokémon (Gen 1, limit 10)
curl "http://localhost:8000/api/pokemon?generation=1&limit=10"

# Get specific Pokémon
curl http://localhost:8000/api/pokemon/25

# Get similar Pokémon
curl "http://localhost:8000/api/similarity/25?top_k=5"

# Get similarity matrix
curl "http://localhost:8000/api/similarity-matrix?generation=1&min_similarity=0.3"

# List generations
curl http://localhost:8000/api/generations
```

### Response Examples

```json
// GET /api/health
{"status": "ok"}

// GET /api/pokemon/25
{
  "id": 25,
  "name": "pikachu",
  "generation": "generation-i",
  "types": ["electric"],
  "height": 4,
  "weight": 60,
  "sprite_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/25.png"
}

// GET /api/similarity/25?top_k=3
[
  {
    "id": 26,
    "name": "raichu",
    "similarity": 0.92,
    "distance": 0.082,
    ...
  },
  {
    "id": 100,
    "name": "voltorb",
    "similarity": 0.78,
    "distance": 0.123,
    ...
  }
]
```

---

## Troubleshooting

### Backend Issues

**Issue**: `ModuleNotFoundError: No module named 'librosa'`

```bash
# Solution: Install dependencies
pip install -r requirements.txt
```

**Issue**: `Address already in use` (port 5000)

```bash
# Find and kill process on port 8000
lsof -i :8000
kill -9 <PID>

# Or use different port (edit app.py)
```

**Issue**: No audio files downloading

```bash
# Check internet connection
# Check if PokéAPI is accessible: curl https://pokeapi.co/api/v2/pokemon/1
# Check backend logs for errors
```

### Frontend Issues

**Issue**: `Failed to fetch from http://localhost:8000`

```bash
# Solution: Ensure backend is running
# Check: http://localhost:8000/api/health should return {"status": "ok"}
```

**Issue**: Graph not appearing

```bash
# Solution:
# 1. Check browser console for errors (F12)
# 2. Ensure similarity data is built
# 3. Wait 2-3 seconds for D3 rendering
```

**Issue**: `npm: command not found`

```bash
# Solution: Install Node.js from nodejs.org
# Then: npm --version (should be 8+)
```

---

## Performance Tips

1. **Start with one generation** for faster initial load
2. **Increase min similarity** to reduce connections and improve performance
3. **Use Chrome DevTools** to profile if slow
4. **Close other browser tabs** when visualizing large graphs

---

## Exploring Patterns

### Bird Pokémon

1. Select Generation 1
2. Look for: Pidgeot, Pidgeotto, Pidgey, Zapdos
3. Notice: Should cluster together (chirping sounds)

### Electric Types

1. Select Generation 1
2. Look for: Pikachu, Raichu, Electabuzz, Jolteon, Magnemite
3. Notice: May have "electric" characteristics

### Evolution Families

1. Find a Pokémon and its evolution (e.g., Bulbasaur → Ivysaur → Venusaur)
2. Check if they appear similar
3. Evolution often changes cry slightly

### Generation Differences

1. Build matrices for Gen 1 vs Gen 5
2. Compare node density and clustering
3. Notice sound quality evolution

---

## Data Files Explained

```
backend/data/
├── cache/
│   ├── pokemon_1.json          # Pikachu full data
│   ├── pokemon-species_1.json  # BulbasaurInfo
│   └── ... (PokéAPI responses)
│
├── cries/
│   ├── 1.ogg                   # Bulbasaur audio
│   ├── 25.ogg                  # Pikachu audio
│   └── ... (all audio files)
│
├── vectors/
│   ├── 1.npy                   # MFCC features
│   ├── 25.npy                  # MFCC features
│   └── ... (all feature vectors)
│
└── similarity_data.json        # Full matrix (precomputed)
```

**Cache sizes**:

- API cache: ~50MB
- Audio files: ~200MB
- Feature vectors: ~10MB
- Similarity matrix: ~5MB

---

## Development Tips

### Modifying Backend

1. Backend has auto-reload (Flask debug mode)
2. Simply save changes to `.py` files
3. Refresh browser to see API changes

### Modifying Frontend

1. Frontend has hot reload
2. Save `.jsx` or `.css` files
3. Browser refreshes automatically

### Adding New Pokémon

1. Already included all 1025 Pokémon
2. Just build matrix for desired generations

### Customizing Similarity Threshold

1. Edit line in `app.py`:

   ```python
   # Default minimum similarity for links
   MIN_SIMILARITY_DEFAULT = 0.3
   ```

2. Or adjust via UI slider (recommended)

---

## Monitoring & Logs

### Backend Logs

- Shows PokéAPI requests and caching
- Audio processing progress
- Similarity computation status

### Browser Console (F12)

- Shows API response times
- D3 rendering performance
- Any JavaScript errors

---

## Resetting Everything

```bash
# Clear all cached data
rm -rf backend/data/cache backend/data/cries backend/data/vectors backend/data/*.json

# Reinstall dependencies
pip install -r backend/requirements.txt --upgrade
npm --prefix frontend install

# Rebuild everything fresh
python manage.py build --force
```

---

## Next Steps

1. ✅ Complete setup (30 minutes first time)
2. 📊 Build similarity matrix (2-5 minutes)
3. 🎵 Explore visualization
4. 🔍 Look for patterns
5. 📈 Analyze findings
6. 🚀 Consider enhancements

Enjoy exploring Pokémon cry signatures! 🎵
