import React, { useState, useEffect } from "react";

const GEN_I_STARTERS = [
  { id: 1, name: "Bulbasaur" },
  { id: 4, name: "Charmander" },
  { id: 7, name: "Squirtle" },
];

// Internal steps: 1=pokéball, 2=click instructions, 3=zoom+dblclick, 4=explanation
// External steps reported to App: 1,2 → 1 (overview), 3 → 2 (zoom), 4 → 3 (detail)
const toExternalStep = (s) => (s <= 2 ? 1 : s - 1);

export const Tutorial = ({
  graphData,
  selectedPokemon,
  tutorialStep: externalStep,
  onStepChange,
  onStarterChange,
  onStarterReveal,
  onComplete,
  onSkip,
}) => {
  const [step, setStep] = useState(1);
  const [selectedStarter, setSelectedStarter] = useState(null);
  const [openedPokeballs, setOpenedPokeballs] = useState(new Set());
  const [openingPokeballs, setOpeningPokeballs] = useState(new Set());
  const [closingPokeball, setClosingPokeball] = useState(null);

  useEffect(() => {
    if (onStepChange) onStepChange(toExternalStep(step));
  }, [step, onStepChange]);

  // Advance from zoom step to explanation when user double-clicks starter
  useEffect(() => {
    if (step !== 3 || selectedPokemon !== selectedStarter) return;
    setStep(4);
  }, [selectedPokemon, selectedStarter, step]);

  const handlePokeballClick = (pokemonId) => {
    if (
      selectedStarter &&
      selectedStarter !== pokemonId &&
      openedPokeballs.has(selectedStarter)
    ) {
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

    setOpeningPokeballs((prev) => {
      const next = new Set(prev);
      next.add(pokemonId);
      return next;
    });
    setSelectedStarter(pokemonId);

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
      if (onStarterReveal) {
        onStarterReveal(pokemonId);
      }
    }, 600);
  };

  // Step 1 → 2: just advance; starter reported to App when entering the zoom step
  const handleContinueFromStep1 = () => {
    setStep(2);
  };

  // Step 2 → 3: now report the starter so the graph zoom triggers
  const handleContinueToZoom = () => {
    if (onStarterChange) onStarterChange(selectedStarter);
    setStep(3);
  };

  // ── Step 1: Pokéball Picker ───────────────────────────────────────────────
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
                  {openedPokeballs.has(starter.id) &&
                    closingPokeball !== starter.id && (
                      <img
                        src={`https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/${starter.id}.png`}
                        alt={starter.name}
                        className="starter-sprite"
                      />
                    )}
                </button>
                {openedPokeballs.has(starter.id) &&
                  closingPokeball !== starter.id && (
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

  // ── Step 2: Click Instructions ────────────────────────────────────────────
  if (step === 2) {
    return (
      <div className="tutorial-step2" aria-label="click instructions">
        <div className="tutorial-dialog tutorial-dialog-step2">
          <h2 className="tutorial-title">Explore the Graph</h2>
          <p className="tutorial-text">
            <strong>Hover any Pokémon</strong> to see its details.{" "}
            <strong>Hover a dotted cluster outline</strong> to learn about that
            sound group.
          </p>
          <p className="tutorial-text" style={{ marginTop: 6 }}>
            <strong>Click any Pokémon</strong> to hear its cry.
          </p>
          <div className="tutorial-buttons">
            <button
              className="tutorial-continue-btn"
              onClick={handleContinueToZoom}
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

  // ── Step 3: Zoom spotlight + double-click instruction ─────────────────────
  if (step === 3 && selectedStarter) {
    const starterName =
      GEN_I_STARTERS.find((s) => s.id === selectedStarter)?.name ||
      "Your Pokémon";

    return (
      <div className="tutorial-step2">
        <div className="tutorial-dialog tutorial-dialog-step2">
          <h2 className="tutorial-title">Found {starterName}!</h2>
          <p className="tutorial-text">
            Double-click on {starterName} in the graph to open its
            Pokémon-specific graph.
          </p>
          <p
            className="tutorial-text"
            style={{ fontSize: "14px", color: "#666" }}
          >
            This will show you which other Pokémon have similar cries.
          </p>
          <button className="tutorial-skip-btn" onClick={onSkip}>
            Skip Tutorial
          </button>
        </div>
      </div>
    );
  }

  // ── Step 4: Explanation ───────────────────────────────────────────────────
  if (step === 4) {
    return (
      <div className="tutorial-overlay">
        <div className="tutorial-modal">
          <h2 className="tutorial-title">Focused Similarity View</h2>
          <div className="tutorial-explanation">
            <p className="tutorial-text">
              <strong>What you're seeing:</strong>
            </p>
            <ul className="tutorial-list">
              <li>The selected Pokémon is in the center</li>
              <li>Other Pokémon are arranged by their cry similarity score</li>
              <li>Closer Pokémon have more similar cries</li>
              <li>Hover over any Pokémon to see the similarity percentage</li>
            </ul>
            <p className="tutorial-text">
              Return to overview mode to see broader audio neighborhoods. Use
              the search bar to center this similarity graph on another Pokémon,
              or double-click any Pokémon to recenter the view there.
            </p>
          </div>
          <div className="tutorial-buttons">
            <button className="tutorial-complete-btn" onClick={onComplete}>
              Got It! ✓
            </button>
          </div>
        </div>
      </div>
    );
  }

  return null;
};
