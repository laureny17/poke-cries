import React, { useEffect } from "react";

export const IntroScreen = ({ onDismiss }) => {
  useEffect(() => {
    // Auto-dismiss after 5 seconds
    const timer = setTimeout(onDismiss, 5000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  return (
    <div className="intro-overlay">
      <div className="intro-modal">
        <h1 className="intro-title">Pokémon Cry Atlas</h1>
        <p className="intro-subtitle">
          Explore how Pokémon cries cluster together by audio similarity.
        </p>
        <p className="intro-description">
          See the overview of all Pokémon, then zoom into individual neighborhoods
          to understand their cry relationships.
        </p>
        <button className="intro-button" onClick={onDismiss}>
          Start Exploring →
        </button>
      </div>
    </div>
  );
};
