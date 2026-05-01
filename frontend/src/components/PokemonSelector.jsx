import React, { useState, useEffect } from "react";
import { apiClient } from "../api/client";
import { LoadingText } from "./LoadingText";

export const PokemonSelector = ({
  generation,
  selectedPokemon,
  onSelect,
  similarPokemon,
}) => {
  const [pokemon, setPokemon] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchPokemon = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await apiClient.getPokemonList(generation);
        setPokemon(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchPokemon();
  }, [generation]);

  if (loading) {
    return (
      <div className="loading">
        <LoadingText label="Loading Pokémon" />
      </div>
    );
  }

  if (error) {
    return <div className="error">Error: {error}</div>;
  }

  const selectedInfo = pokemon.find((p) => p.id === selectedPokemon);

  return (
    <div className="sidebar">
      {selectedInfo ? (
        <div className="info-panel">
          <div style={{ textAlign: "center", marginBottom: "15px" }}>
            <img
              src={selectedInfo.sprite_url}
              alt={selectedInfo.name}
              style={{ width: "80px", height: "80px" }}
            />
          </div>
          <p>
            <span className="info-label">Name:</span> {selectedInfo.name}
          </p>
          <p>
            <span className="info-label">ID:</span> #{selectedInfo.id}
          </p>
          <p>
            <span className="info-label">Generation:</span>{" "}
            {selectedInfo.generation.replace("generation-", "Gen ")}
          </p>
          <p>
            <span className="info-label">Type:</span>{" "}
            {selectedInfo.types.join(", ")}
          </p>
          <p>
            <span className="info-label">Height:</span>{" "}
            {(selectedInfo.height / 10).toFixed(1)}m
          </p>
          <p>
            <span className="info-label">Weight:</span>{" "}
            {(selectedInfo.weight / 10).toFixed(1)}kg
          </p>
        </div>
      ) : null}

      {similarPokemon && similarPokemon.length > 0 && (
        <div>
          <h3>Most Similar</h3>
          {similarPokemon.slice(0, 10).map((poke) => (
            <div
              key={poke.id}
              className="pokemon-item"
              onClick={() => onSelect(poke.id)}
            >
              <img src={poke.sprite_url} alt={poke.name} />
              <div>
                <div className="pokemon-name">{poke.name}</div>
                <div className="pokemon-similarity">
                  Similarity: {(poke.similarity * 100).toFixed(1)}%
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {!selectedInfo && (
        <div>
          <h3>Select a Pokémon</h3>
          {pokemon.map((poke) => (
            <div
              key={poke.id}
              className={`pokemon-item ${
                poke.id === selectedPokemon ? "selected" : ""
              }`}
              onClick={() => onSelect(poke.id)}
            >
              <img src={poke.sprite_url} alt={poke.name} />
              <span>{poke.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
