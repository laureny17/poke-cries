import React, { useState, useEffect } from "react";
import { apiClient } from "../api/client";

export const GenerationFilter = ({ value, onChange }) => {
  const [generations, setGenerations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchGenerations = async () => {
      try {
        setLoading(true);
        const data = await apiClient.getGenerations();
        setGenerations(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchGenerations();
  }, []);

  if (loading) return <div className="control-group">Loading...</div>;
  if (error) return <div className="control-group error">Error: {error}</div>;

  return (
    <div className="control-group">
      <label htmlFor="generation">Generation</label>
      <select
        id="generation"
        value={value || ""}
        onChange={(e) =>
          onChange(e.target.value ? parseInt(e.target.value) : null)
        }
      >
        <option value="">All Generations</option>
        {generations.map((gen) => (
          <option key={gen.id} value={gen.id}>
            {gen.name} ({gen.pokemon_count} Pokémon)
          </option>
        ))}
      </select>
    </div>
  );
};
