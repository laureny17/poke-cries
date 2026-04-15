import React, { useMemo, useState, useEffect, forwardRef } from "react";
import { TYPE_COLORS } from "../typeColors";

const GEN_LABELS = {
  "generation-i": "GEN I",
  "generation-ii": "GEN II",
  "generation-iii": "GEN III",
  "generation-iv": "GEN IV",
  "generation-v": "GEN V",
  "generation-vi": "GEN VI",
  "generation-vii": "GEN VII",
  "generation-viii": "GEN VIII",
  "generation-ix": "GEN IX",
};

export const SettingsPanel = forwardRef(
  (
    {
      nodes,
      excludedGenerations,
      excludedTypes,
      lockedGenerations = new Set(),
      lockedTypes = new Set(),
      overMaxGens = new Set(),
      overMaxTypes = new Set(),
      maxNodes = 400,
      filteredCount = 0,
      onToggleGeneration,
      onToggleType,
    },
    ref,
  ) => {
    // Key of the item currently showing the "max exceeded" tooltip.
    const [maxTooltipKey, setMaxTooltipKey] = useState(null);

    useEffect(() => {
      if (!maxTooltipKey) return undefined;
      const t = setTimeout(() => setMaxTooltipKey(null), 2500);
      return () => clearTimeout(t);
    }, [maxTooltipKey]);

    const generations = useMemo(() => {
      const gens = new Set(nodes.map((n) => n.generation).filter(Boolean));
      return Array.from(gens).sort();
    }, [nodes]);

    const types = useMemo(() => {
      const ts = new Set(nodes.flatMap((n) => n.types || []).filter(Boolean));
      return Array.from(ts).sort();
    }, [nodes]);

    const handleGenClick = (gen) => {
      if (lockedGenerations.has(gen)) return;
      if (overMaxGens.has(gen)) {
        setMaxTooltipKey(`gen-${gen}`);
        return;
      }
      onToggleGeneration(gen);
    };

    const handleTypeClick = (type) => {
      if (lockedTypes.has(type)) return;
      if (overMaxTypes.has(type)) {
        setMaxTooltipKey(`type-${type}`);
        return;
      }
      onToggleType(type);
    };

    return (
      <div className="settings-panel" ref={ref}>
        <div className="settings-count-bar">
          {filteredCount} / {maxNodes} shown
        </div>

        <div className="settings-section">
          <div className="settings-section-title">GENERATION</div>
          {generations.map((gen) => {
            const locked = lockedGenerations.has(gen);
            const overMax = overMaxGens.has(gen);
            const tooltipKey = `gen-${gen}`;
            return (
              <div key={gen} className="settings-item-wrap">
                <label
                  className={`settings-check-label${locked || overMax ? " settings-check-locked" : ""}`}
                  onClick={(e) => {
                    e.preventDefault();
                    handleGenClick(gen);
                  }}
                >
                  <input
                    type="checkbox"
                    checked={!excludedGenerations.has(gen)}
                    disabled={locked || overMax}
                    onChange={() => {}}
                  />
                  {GEN_LABELS[gen] || gen.toUpperCase()}
                </label>
                {maxTooltipKey === tooltipKey && (
                  <div className="settings-max-tooltip">
                    Max {maxNodes} — hide another first
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="settings-section">
          <div className="settings-section-title">TYPE</div>
          <div className="settings-types-grid">
            {types.map((type) => {
              const locked = lockedTypes.has(type);
              const overMax = overMaxTypes.has(type);
              const tooltipKey = `type-${type}`;
              return (
                <div key={type} className="settings-item-wrap">
                  <label
                    className={`settings-check-label${locked || overMax ? " settings-check-locked" : ""}`}
                    style={{
                      color:
                        locked || overMax
                          ? `${TYPE_COLORS[type] || "#555"}88`
                          : TYPE_COLORS[type] || "#555",
                    }}
                    onClick={(e) => {
                      e.preventDefault();
                      handleTypeClick(type);
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={!excludedTypes.has(type)}
                      disabled={locked || overMax}
                      onChange={() => {}}
                    />
                    {type.toUpperCase()}
                  </label>
                  {maxTooltipKey === tooltipKey && (
                    <div className="settings-max-tooltip">
                      Max {maxNodes} — hide another first
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  },
);

SettingsPanel.displayName = "SettingsPanel";
