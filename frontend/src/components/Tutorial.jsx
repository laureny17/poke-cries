import React, { useState, useEffect } from "react";

const GEN_I_STARTERS = [
  { id: 1, name: "Bulbasaur" },
  { id: 4, name: "Charmander" },
  { id: 7, name: "Squirtle" },
];

export const Tutorial = ({
  graphData,
  selectedPokemon,
  tutorialStep: externalStep,
  onStepChange,
  onComplete,
  onSkip
}) => {
  const [step, setStep] = useState(1);
  const [selectedStarter, setSelectedStarter] = useState(null);
  const [openedPokeballs, setOpenedPokeballs] = useState(new Set());
  const [openingPokeballs, setOpeningPokeballs] = useState(new Set());
  const [closingPokeball, setClosingPokeball] = useState(null);

  // Sync internal step with parent
  useEffect(() => {
    if (onStepChange) {
      onStepChange(step);
    }
  }, [step, onStepChange]);

  const handlePokeballClick = (pokemonId) => {
    // If clicking a different pokéball, close the previous one first
    if (selectedStarter && selectedStarter !== pokemonId && openedPokeballs.has(selectedStarter)) {
      setClosingPokeball(selectedStarter);
      setTimeout(() => {
        setOpenedPokeballs((prev) => {
          const next = new Set(prev);
          next.delete(selectedStarter);
          return next;
        });
        setClosingPokeball(null);
      }, 600);
    }

    // Start opening animation
    setOpeningPokeballs((prev) => {
      const next = new Set(prev);
      next.add(pokemonId);
      return next;
    });
    setSelectedStarter(pokemonId);

    // Transition to fully opened after animation
    setTimeout(() => {
      setOpeningPokeballs((prev) => {
        const next = new Set(prev);
        next.delete(pokemonId);
        return next;
      });
      setOpenedPokeballs((prev) => {
        const next = new Set(prev);
        next.add(pokemonId);
        return next;
      });
    }, 600);
  };

  const handleContinueFromStep1 = () => {
    setStep(2);
  };

  const handleDoubleClickAdvance = () => {
    setStep(3);
  };

  // Listen for double-click on selected pokemon to advance from step 2
  useEffect(() => {
    if (step !== 2 || selectedPokemon !== selectedStarter) {
      return;
    }

    // The SimilarityGraph will handle the double-click; we'll detect it via selectedPokemon
    handleDoubleClickAdvance();
  }, [selectedPokemon, selectedStarter, step]);

  const handleComplete = () => {
    onComplete();
  };

  const handleSkip = () => {
    onSkip();
  };

  // Step 1: Pokéball Picker
  if (step === 1) {
    return (
      <div className="tutorial-overlay">
        <div className="tutorial-modal">
          <h2 className="tutorial-title">Choose Your Starter Pokémon</h2>
          <p className="tutorial-text">
            Click on a Pokéball to reveal which starter you get!
          </p>
          <div className="pokeball-picker">
            {GEN_I_STARTERS.map((starter) => (
              <div key={starter.id} className="pokeball-container">
                <button
                  className={`pokeball ${
                    closingPokeball === starter.id ? "closing" : ""
                  } ${openedPokeballs.has(starter.id) ? "open" : ""} ${
                    selectedStarter === starter.id ? "selected" : ""
                  } ${
                    selectedStarter && selectedStarter !== starter.id
                      ? "inactive"
                      : ""
                  }`}
                  onClick={() => handlePokeballClick(starter.id)}
                  aria-label={`Click to reveal ${starter.name}`}
                  style={{
                    backgroundImage:
                      closingPokeball === starter.id
                        ? `url(/assets/pokeball-closed.svg)`
                        : openingPokeballs.has(starter.id)
                        ? `url(/assets/pokeball-opening.svg)`
                        : openedPokeballs.has(starter.id)
                        ? `url(/assets/pokeball-open.svg)`
                        : `url(/assets/pokeball-closed.svg)`,
                  }}
                >
                  {openedPokeballs.has(starter.id) && closingPokeball !== starter.id && (
                    <img
                      src={`https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/${starter.id}.png`}
                      alt={starter.name}
                      className="starter-sprite"
                    />
                  )}
                </button>
                {openedPokeballs.has(starter.id) && closingPokeball !== starter.id && (
                  <div className="starter-name">{starter.name}</div>
                )}
              </div>
            ))}
          </div>
          <div className="tutorial-buttons">
            <button
              className="tutorial-continue-btn"
              onClick={handleContinueFromStep1}
              disabled={!selectedStarter}
            >
              Continue →
            </button>
          </div>
          <button className="tutorial-skip-btn" onClick={onSkip}>
            Skip Tutorial
          </button>
        </div>
      </div>
    );
  }

  // Step 2: Spotlight Effect
  if (step === 2 && selectedStarter) {
    const starterName = GEN_I_STARTERS.find((s) => s.id === selectedStarter)?.name || "Your Pokémon";

    return (
      <div className="tutorial-step2">
        <div className="tutorial-dim-overlay" />
        <div className="tutorial-highlight-box">
          <div className="tutorial-cursor">👆</div>
        </div>
        <div className="tutorial-dialog tutorial-dialog-step2">
          <h2 className="tutorial-title">Found {starterName}!</h2>
          <p className="tutorial-text">
            Double-click on {starterName} in the graph to see its audio neighborhood.
          </p>
          <p className="tutorial-text" style={{ fontSize: "14px", color: "#666" }}>
            This will show you which other Pokémon have similar cries.
          </p>
          <button className="tutorial-skip-btn" onClick={handleSkip}>
            Skip Tutorial
          </button>
        </div>
      </div>
    );
  }

  // Step 3: Explanation
  if (step === 3) {
    return (
      <div className="tutorial-overlay">
        <div className="tutorial-modal">
          <h2 className="tutorial-title">Audio Neighborhood Unlocked!</h2>
          <div className="tutorial-explanation">
            <p className="tutorial-text">
              <strong>What you're seeing:</strong>
            </p>
            <ul className="tutorial-list">
              <li>The selected Pokémon is in the center</li>
              <li>
                Other Pokémon are arranged by how similar their cries are
              </li>
              <li>Closer Pokémon have more similar cries</li>
              <li>Hover over any Pokémon to see the similarity percentage</li>
            </ul>
            <p className="tutorial-text">
              <strong>Pro Tip:</strong> You can zoom and pan the graph. Use the
              search bar to jump to specific Pokémon!
            </p>
          </div>
          <div className="tutorial-buttons">
            <button className="tutorial-complete-btn" onClick={handleComplete}>
              Got It! ✓
            </button>
          </div>
        </div>
      </div>
    );
  }

  return null;
};
