import React from "react";

export const IntroScreen = ({ onStartExploring, onStartTutorial }) => {
  return (
    <div className="intro-overlay">
      <div className="intro-modal">
        <h1 className="intro-title">Pokémon Cry Atlas</h1>
        <p className="intro-subtitle">
          Explore how Pokémon cries cluster together by audio similarity.
        </p>
        <p className="intro-description">
          See the overview of all Pokémon, then zoom into individual
          neighborhoods to understand their cry relationships.
        </p>
        <div className="intro-actions">
          <button className="intro-button" onClick={onStartExploring}>
            Start Exploring
          </button>
          <button
            className="intro-button intro-button-secondary"
            onClick={onStartTutorial}
          >
            Tutorial
          </button>
        </div>
      </div>
    </div>
  );
};
