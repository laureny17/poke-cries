import axios from 'axios';

const normalizeApiBase = (url) => {
  const trimmedUrl = String(url || '').replace(/\/+$/, '');
  return trimmedUrl.endsWith('/api') ? trimmedUrl : `${trimmedUrl}/api`;
};

const API_BASE = normalizeApiBase(
  process.env.REACT_APP_API_URL || 'http://localhost:8000/api'
);

export const apiClient = {
  // Get all Pokémon with optional filters
  getPokemonList: async (generation = null, limit = 100) => {
    try {
      const params = new URLSearchParams();
      if (generation) params.append('generation', generation);
      params.append('limit', limit);

      const response = await axios.get(`${API_BASE}/pokemon?${params}`);
      return response.data;
    } catch (error) {
      console.error('Error fetching Pokémon list:', error);
      throw error;
    }
  },

  // Get specific Pokémon
  getPokemon: async (pokemonId) => {
    try {
      const response = await axios.get(`${API_BASE}/pokemon/${pokemonId}`);
      return response.data;
    } catch (error) {
      console.error(`Error fetching Pokémon ${pokemonId}:`, error);
      throw error;
    }
  },

  // Get enriched details for tooltip/audio playback
  getPokemonDetails: async (pokemonId) => {
    try {
      const response = await axios.get(`${API_BASE}/pokemon/${pokemonId}`);
      return response.data;
    } catch (error) {
      console.error(`Error fetching Pokémon details ${pokemonId}:`, error);
      throw error;
    }
  },

  // Get similar Pokémon
  getSimilarPokemon: async (pokemonId, topK = 20, minSimilarity = 0.5) => {
    try {
      const params = new URLSearchParams();
      params.append('top_k', topK);
      params.append('min_similarity', minSimilarity);

      const response = await axios.get(
        `${API_BASE}/similarity/${pokemonId}?${params}`
      );
      return response.data;
    } catch (error) {
      console.error(`Error fetching similar Pokémon for ${pokemonId}:`, error);
      throw error;
    }
  },

  // Get similarity matrix for visualization
  getSimilarityMatrix: async (generation = null, minSimilarity = 0.0) => {
    try {
      const params = new URLSearchParams();
      if (generation) params.append('generation', generation);
      params.append('min_similarity', minSimilarity);

      const response = await axios.get(
        `${API_BASE}/similarity-matrix?${params}`
      );
      return response.data;
    } catch (error) {
      console.error('Error fetching similarity matrix:', error);
      throw error;
    }
  },

  // Get available generations
  getGenerations: async () => {
    try {
      const response = await axios.get(`${API_BASE}/generations`);
      return response.data;
    } catch (error) {
      console.error('Error fetching generations:', error);
      throw error;
    }
  },

  // Build similarity matrix (admin endpoint)
  buildSimilarityMatrix: async (generation = null, force = false) => {
    try {
      const response = await axios.post(
        `${API_BASE}/admin/build-matrix`,
        { generation, force }
      );
      return response.data;
    } catch (error) {
      console.error('Error building similarity matrix:', error);
      throw error;
    }
  },
};
