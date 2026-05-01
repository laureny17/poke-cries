import React, {
  useState,
  useEffect,
  useMemo,
  useRef,
  useCallback,
} from "react";
import { SimilarityGraph } from "./components/SimilarityGraph";
import { SearchBar } from "./components/SearchBar";
import { SettingsPanel } from "./components/SettingsPanel";
import { IntroScreen } from "./components/IntroScreen";
import { Tutorial } from "./components/Tutorial";
import { apiClient } from "./api/client";
import "./App.css";

// Max Pokémon shown in the overview graph at once.
// Keeps the force simulation fast and the graph readable.
const MAX_NODES = 400;
const GRAPH_CACHE_KEY = "poke-cries:similarity-matrix:v12";
const DEFAULT_GENERATION = "generation-i";

export default function App() {
  const [selectedPokemon, setSelectedPokemon] = useState(null);
  const [focusTarget, setFocusTarget] = useState(null);
  const [similarPokemon, setSimilarPokemon] = useState([]);
  const [graphData, setGraphData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedGraphLoading, setSelectedGraphLoading] = useState(false);
  const [error, setError] = useState(null);
  const [pokemonDetailsById, setPokemonDetailsById] = useState({});
  const pokemonDetailsRequestsRef = useRef({});
  const activeCryRef = useRef(null);

  // Intro & Tutorial state
  const [showIntro, setShowIntro] = useState(true);
  const [showTutorial, setShowTutorial] = useState(false);
  const [tutorialStep, setTutorialStep] = useState(1);
  const [tutorialSelectedStarter, setTutorialSelectedStarter] = useState(null);

  // Filter state — empty Set means "no filter applied" (show all).
  // Starts restrictive (all gens excluded); initialised to Gen I once data loads.
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [excludedGenerations, setExcludedGenerations] = useState(new Set());
  const [excludedTypes, setExcludedTypes] = useState(new Set());

  const settingsBtnRef = useRef();
  const settingsPanelRef = useRef();

  const handleStartExploring = useCallback(() => {
    setShowIntro(false);
    setShowTutorial(false);
    setTutorialStep(1);
    setTutorialSelectedStarter(null);
  }, []);

  const handleStartTutorial = useCallback(() => {
    setShowIntro(false);
    setShowTutorial(true);
    setTutorialStep(1);
    setTutorialSelectedStarter(null);
    setSelectedPokemon(null);
  }, []);

  const handleCompleteTutorial = useCallback(() => {
    setShowTutorial(false);
    setTutorialStep(1);
    setTutorialSelectedStarter(null);
  }, []);

  const handleSkipTutorial = useCallback(() => {
    setShowTutorial(false);
    setTutorialStep(1);
    setTutorialSelectedStarter(null);
  }, []);

  const handleSearchSelect = useCallback((pokemonId) => {
    setFocusTarget((prev) => ({ id: pokemonId, seq: (prev?.seq ?? 0) + 1 }));
  }, []);

  const getDefaultExcludedGenerations = useCallback((nodes = []) => {
    const allGens = new Set(nodes.map((n) => n.generation).filter(Boolean));
    allGens.delete(DEFAULT_GENERATION);
    return allGens;
  }, []);

  const handlePokemonSelect = useCallback((pokemonId) => {
    if (pokemonId === selectedPokemon) {
      return;
    }
    setSimilarPokemon([]);
    setSelectedPokemon(pokemonId);
  }, [selectedPokemon]);

  useEffect(() => {
    setFocusTarget(null);
  }, [selectedPokemon]);

  // Close settings panel on outside click
  useEffect(() => {
    if (!settingsOpen) return undefined;
    const handler = (e) => {
      if (
        !settingsBtnRef.current?.contains(e.target) &&
        !settingsPanelRef.current?.contains(e.target)
      ) {
        setSettingsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [settingsOpen]);

  // On first data load, default to showing Gen I only.
  useEffect(() => {
    if (!graphData) return;
    setExcludedGenerations(getDefaultExcludedGenerations(graphData.nodes));
  }, [graphData, getDefaultExcludedGenerations]); // graphData only transitions once: null → loaded

  const resetFilters = useCallback(() => {
    setSelectedPokemon(null);
    setExcludedGenerations(getDefaultExcludedGenerations(graphData?.nodes));
    setExcludedTypes(new Set());
  }, [getDefaultExcludedGenerations, graphData]);

  const toggleGeneration = useCallback(
    (gen, filteredNodes, excludedTypes) => {
      // Hiding a gen is always allowed.
      if (!excludedGenerations.has(gen)) {
        setExcludedGenerations((prev) => {
          const n = new Set(prev);
          n.add(gen);
          return n;
        });
        return false;
      }
      // Showing a gen: check we won't exceed MAX_NODES.
      const wouldAdd = (graphData?.nodes || []).filter(
        (n) =>
          n.generation === gen &&
          (excludedTypes.size === 0 ||
            (n.types || []).some((t) => !excludedTypes.has(t))),
      ).length;
      if (filteredNodes.length + wouldAdd > MAX_NODES) return true; // blocked
      setExcludedGenerations((prev) => {
        const n = new Set(prev);
        n.delete(gen);
        return n;
      });
      return false;
    },
    [excludedGenerations, graphData],
  );

  const toggleType = useCallback(
    (type, filteredNodes, excludedGenerations) => {
      // Hiding a type is always allowed.
      if (!excludedTypes.has(type)) {
        setExcludedTypes((prev) => {
          const n = new Set(prev);
          n.add(type);
          return n;
        });
        return false;
      }
      // Showing a type: count nodes that would become newly visible.
      const wouldAdd = (graphData?.nodes || []).filter(
        (n) =>
          !excludedGenerations.has(n.generation) &&
          (n.types || []).includes(type) &&
          (n.types || []).every((t) => t === type || excludedTypes.has(t)),
      ).length;
      if (filteredNodes.length + wouldAdd > MAX_NODES) return true; // blocked
      setExcludedTypes((prev) => {
        const n = new Set(prev);
        n.delete(type);
        return n;
      });
      return false;
    },
    [excludedTypes, graphData],
  );

  const ensurePokemonDetails = async (pokemonId) => {
    if (!pokemonId) return null;
    if (pokemonDetailsById[pokemonId]) return pokemonDetailsById[pokemonId];
    if (pokemonDetailsRequestsRef.current[pokemonId]) {
      return pokemonDetailsRequestsRef.current[pokemonId];
    }

    const request = apiClient
      .getPokemonDetails(pokemonId)
      .then((details) => {
        setPokemonDetailsById((previous) => ({
          ...previous,
          [pokemonId]: details,
        }));
        return details;
      })
      .catch((err) => {
        console.error("Error fetching pokemon details:", err);
        return null;
      })
      .finally(() => {
        delete pokemonDetailsRequestsRef.current[pokemonId];
      });

    pokemonDetailsRequestsRef.current[pokemonId] = request;
    return request;
  };

  const playPokemonCry = async (pokemonId) => {
    const details = await ensurePokemonDetails(pokemonId);
    const cryUrl =
      // for pikachu, use the legacy cry which is better for comparison
      pokemonId === 25
        ? details?.cry_url_legacy || details?.cry_url
        : details?.cry_url || details?.cry_url_legacy;
    if (!cryUrl) return;
    try {
      if (activeCryRef.current) {
        activeCryRef.current.pause();
        activeCryRef.current.currentTime = 0;
      }
      const audio = new Audio(cryUrl);
      activeCryRef.current = audio;
      audio.volume = 0.75;
      audio.addEventListener("ended", () => {
        if (activeCryRef.current === audio) {
          activeCryRef.current = null;
        }
      });
      await audio.play();
    } catch (err) {
      console.error("Error playing cry audio:", err);
    }
  };

  // Load the broad similarity matrix once on mount
  useEffect(() => {
    const loadMatrix = async () => {
      let hasCachedData = false;

      try {
        const cached = window.localStorage.getItem(GRAPH_CACHE_KEY);
        if (cached) {
          const parsed = JSON.parse(cached);
          if (parsed?.nodes && parsed?.links) {
            setGraphData(parsed);
            hasCachedData = true;
          }
        }
      } catch (err) {
        console.warn("Error reading cached similarity matrix:", err);
      }

      try {
        setLoading(!hasCachedData);
        setError(null);
        const data = await apiClient.getSimilarityMatrix(null, 0.15, false);
        setGraphData(data);
        try {
          window.localStorage.setItem(GRAPH_CACHE_KEY, JSON.stringify(data));
        } catch (err) {
          console.warn("Error caching similarity matrix:", err);
        }
      } catch (err) {
        if (!hasCachedData) {
          setError(err.message);
        }
      } finally {
        setLoading(false);
      }
    };
    loadMatrix();
  }, []);

  // Load the larger neighborhood when selected pokemon changes
  useEffect(() => {
    let isCancelled = false;

    const loadSimilar = async () => {
      if (!selectedPokemon || !graphData) {
        setSimilarPokemon([]);
        setSelectedGraphLoading(false);
        return;
      }

      setSelectedGraphLoading(true);
      try {
        // Fetch a broad candidate pool so selected view can reflect filter changes
        // without silently dropping less-similar pokemon.
        const data = await apiClient.getSimilarPokemon(
          selectedPokemon,
          2000,
          0.0,
        );
        if (isCancelled) return;
        setSimilarPokemon(
          data.map((pokemon) => ({
            ...pokemon,
            calibrated_similarity: pokemon.similarity,
            similarity: pokemon.raw_similarity ?? pokemon.similarity,
          })),
        );
      } catch (err) {
        console.error("Error loading similar pokemon:", err);
      } finally {
        if (!isCancelled) {
          setSelectedGraphLoading(false);
        }
      }
    };

    loadSimilar();

    return () => {
      isCancelled = true;
    };
  }, [selectedPokemon, graphData]);

  const selectedNode = graphData?.nodes?.find(
    (node) => node.pokemon_id === selectedPokemon,
  );

  // When a pokemon is selected, make sure its gen + types are never excluded —
  // it would be confusing if selecting a pokemon hid it from the graph.
  useEffect(() => {
    if (!selectedNode) return;
    const { generation, types = [] } = selectedNode;

    setExcludedGenerations((prev) => {
      if (!generation || !prev.has(generation)) return prev;
      const next = new Set(prev);
      next.delete(generation);
      return next;
    });

    setExcludedTypes((prev) => {
      const toRemove = types.filter((t) => prev.has(t));
      if (toRemove.length === 0) return prev;
      const next = new Set(prev);
      toRemove.forEach((t) => next.delete(t));
      return next;
    });
  }, [selectedNode]);

  // Which gen/types the user is not allowed to exclude (the selected pokemon's own).
  const lockedGenerations = useMemo(() => {
    if (!selectedNode?.generation) return new Set();
    return new Set([selectedNode.generation]);
  }, [selectedNode]);

  const lockedTypes = useMemo(() => {
    if (!selectedNode?.types?.length) return new Set();
    return new Set(selectedNode.types);
  }, [selectedNode]);

  const similarityById = useMemo(
    () =>
      similarPokemon.reduce((acc, pokemon) => {
        acc[pokemon.id] = pokemon.similarity;
        return acc;
      }, {}),
    [similarPokemon],
  );

  // Client-side filtering
  const filteredNodes = useMemo(() => {
    if (!graphData) return [];
    return graphData.nodes.filter((node) => {
      const genOk =
        excludedGenerations.size === 0 ||
        !excludedGenerations.has(node.generation);
      const typeOk =
        excludedTypes.size === 0 ||
        (node.types || []).some((t) => !excludedTypes.has(t));
      return genOk && typeOk;
    });
  }, [graphData, excludedGenerations, excludedTypes]);

  const filteredNodeIdxSet = useMemo(
    () => new Set(filteredNodes.map((n) => n.id)),
    [filteredNodes],
  );

  const filteredLinks = useMemo(() => {
    if (!graphData) return [];
    return graphData.links.filter((link) => {
      const src =
        typeof link.source === "object" ? link.source.id : link.source;
      const tgt =
        typeof link.target === "object" ? link.target.id : link.target;
      return filteredNodeIdxSet.has(src) && filteredNodeIdxSet.has(tgt);
    });
  }, [graphData, filteredNodeIdxSet]);

  const visibleClusterNodes = useMemo(() => {
    if (selectedPokemon || filteredNodes.length === 0) return filteredNodes;

    const minVisibleClusterSize = 3;
    const clusterByPokemonId = new Map(
      filteredNodes.map((node) => [node.pokemon_id, node.cluster_id]),
    );
    const nodeByGraphId = new Map(filteredNodes.map((node) => [node.id, node]));
    const nodeByPokemonId = new Map(
      filteredNodes.map((node) => [node.pokemon_id, node]),
    );

    const countClusters = () => {
      const counts = new Map();
      clusterByPokemonId.forEach((clusterId) => {
        counts.set(clusterId, (counts.get(clusterId) || 0) + 1);
      });
      return counts;
    };

    const nearestLinks = [];
    const seenNearestLinks = new Set();
    filteredNodes.forEach((node) => {
      (node.nearest_neighbors || []).forEach((neighbor) => {
        const neighborNode = nodeByPokemonId.get(neighbor.pokemon_id);
        if (!neighborNode) return;
        const [a, b] = [node.id, neighborNode.id].sort((left, right) => left - right);
        const key = `${a}|${b}`;
        if (seenNearestLinks.has(key)) return;
        seenNearestLinks.add(key);
        nearestLinks.push({
          source: node.id,
          target: neighborNode.id,
          similarity: neighbor.similarity || 0,
        });
      });
    });

    const sortedLinks = [...filteredLinks, ...nearestLinks]
      .map((link) => {
        const source =
          typeof link.source === "object" ? link.source.id : link.source;
        const target =
          typeof link.target === "object" ? link.target.id : link.target;
        return { source, target, similarity: link.similarity || 0 };
      })
      .filter(
        (link) =>
          nodeByGraphId.has(link.source) && nodeByGraphId.has(link.target),
      )
      .sort((a, b) => b.similarity - a.similarity);

    for (let pass = 0; pass < 3; pass += 1) {
      const counts = countClusters();
      const tinyNodes = filteredNodes.filter(
        (node) => (counts.get(clusterByPokemonId.get(node.pokemon_id)) || 0) < minVisibleClusterSize,
      );
      if (tinyNodes.length === 0) break;

      let changed = false;
      tinyNodes.forEach((node) => {
        const currentCluster = clusterByPokemonId.get(node.pokemon_id);
        const bestLink = sortedLinks.find((link) => {
          if (link.source !== node.id && link.target !== node.id) return false;
          const neighborId = link.source === node.id ? link.target : link.source;
          const neighbor = nodeByGraphId.get(neighborId);
          if (!neighbor) return false;
          const neighborCluster = clusterByPokemonId.get(neighbor.pokemon_id);
          return (
            neighborCluster !== currentCluster &&
            (counts.get(neighborCluster) || 0) >= minVisibleClusterSize
          );
        });

        if (!bestLink) return;
        const neighborId = bestLink.source === node.id ? bestLink.target : bestLink.source;
        const neighbor = nodeByGraphId.get(neighborId);
        clusterByPokemonId.set(
          node.pokemon_id,
          clusterByPokemonId.get(neighbor.pokemon_id),
        );
        changed = true;
      });

      if (!changed) break;
    }

    const finalCounts = countClusters();
    return filteredNodes.map((node) => {
      const clusterId = clusterByPokemonId.get(node.pokemon_id);
      return {
        ...node,
        cluster_id: clusterId,
        cluster_size: finalCounts.get(clusterId) || node.cluster_size,
      };
    });
  }, [filteredLinks, filteredNodes, selectedPokemon]);

  // Which excluded gens/types, if un-excluded, would push the count over MAX_NODES.
  // Passed to SettingsPanel so it can show a tooltip on those checkboxes.
  const overMaxGens = useMemo(() => {
    if (!graphData) return new Set();
    const result = new Set();
    for (const gen of excludedGenerations) {
      const wouldAdd = graphData.nodes.filter(
        (n) =>
          n.generation === gen &&
          (excludedTypes.size === 0 ||
            (n.types || []).some((t) => !excludedTypes.has(t))),
      ).length;
      if (filteredNodes.length + wouldAdd > MAX_NODES) result.add(gen);
    }
    return result;
  }, [graphData, excludedGenerations, excludedTypes, filteredNodes]);

  const overMaxTypes = useMemo(() => {
    if (!graphData) return new Set();
    const result = new Set();
    for (const type of excludedTypes) {
      const wouldAdd = graphData.nodes.filter(
        (n) =>
          !excludedGenerations.has(n.generation) &&
          (n.types || []).includes(type) &&
          (n.types || []).every((t) => t === type || excludedTypes.has(t)),
      ).length;
      if (filteredNodes.length + wouldAdd > MAX_NODES) result.add(type);
    }
    return result;
  }, [graphData, excludedGenerations, excludedTypes, filteredNodes]);

  const activeFilterCount = excludedGenerations.size + excludedTypes.size;
  const showCenteredLoading =
    loading || (selectedPokemon && selectedGraphLoading);

  return (
    <div className="app-fullscreen">
      {error && <div className="error-overlay">Error: {error}</div>}

      {showIntro && !loading && graphData && (
        <IntroScreen
          onStartExploring={handleStartExploring}
          onStartTutorial={handleStartTutorial}
        />
      )}

      {showTutorial && graphData && !showIntro && (
        <Tutorial
          graphData={graphData}
          selectedPokemon={selectedPokemon}
          tutorialStep={tutorialStep}
          onStepChange={setTutorialStep}
          onStarterChange={setTutorialSelectedStarter}
          onStarterReveal={playPokemonCry}
          onComplete={handleCompleteTutorial}
          onSkip={handleSkipTutorial}
        />
      )}

      {graphData && !showTutorial && !showIntro && (
        <SearchBar
          nodes={filteredNodes}
          onSelect={handleSearchSelect}
          resetKey={selectedPokemon || "overview"}
        />
      )}

      {selectedPokemon && !showTutorial ? (
        <button
          className="overview-btn"
          onClick={() => setSelectedPokemon(null)}
        >
          ← OVERVIEW
        </button>
      ) : null}

      <button
        ref={settingsBtnRef}
        className="settings-btn"
        onClick={() => setSettingsOpen((o) => !o)}
        style={{ display: showTutorial || showIntro ? "none" : "block" }}
      >
        ▼ FILTER{activeFilterCount > 0 ? ` (${activeFilterCount})` : ""}
      </button>

      {settingsOpen && graphData && !showTutorial && !showIntro && (
        <SettingsPanel
          ref={settingsPanelRef}
          nodes={graphData.nodes}
          excludedGenerations={excludedGenerations}
          excludedTypes={excludedTypes}
          lockedGenerations={lockedGenerations}
          lockedTypes={lockedTypes}
          overMaxGens={overMaxGens}
          overMaxTypes={overMaxTypes}
          maxNodes={MAX_NODES}
          filteredCount={filteredNodes.length}
          onToggleGeneration={(gen) =>
            toggleGeneration(gen, filteredNodes, excludedTypes)
          }
          onToggleType={(type) =>
            toggleType(type, filteredNodes, excludedGenerations)
          }
          onResetFilters={resetFilters}
        />
      )}

      {showCenteredLoading ? (
        <div className="center-loading">Loading ...</div>
      ) : graphData ? (
        <SimilarityGraph
          nodes={visibleClusterNodes}
          links={filteredLinks}
          selectedPokemon={selectedPokemon}
          onPokemonSelect={handlePokemonSelect}
          onPokemonClick={playPokemonCry}
          onPokemonHover={ensurePokemonDetails}
          focusTarget={focusTarget}
          similarPokemon={similarPokemon}
          similarityById={similarityById}
          selectedNode={selectedNode}
          pokemonDetailsById={pokemonDetailsById}
          tutorialStep={showTutorial ? tutorialStep : null}
          tutorialSelectedStarter={
            showTutorial ? tutorialSelectedStarter : null
          }
        />
      ) : (
        <div className="loading-overlay">No data available</div>
      )}
    </div>
  );
}
