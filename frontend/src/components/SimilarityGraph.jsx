import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import * as d3 from "d3";
import { TYPE_COLORS } from "../typeColors";

const titleCase = (value) =>
  String(value || "")
    .replace(/-/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");

const formatGeneration = (value) => {
  const raw = String(value || "");
  const roman = raw.replace("generation-", "");
  return roman ? `Gen ${roman.toUpperCase()}` : "";
};

const formatDescription = (value) => {
  const text = String(value || "").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
};

export const SimilarityGraph = ({
  nodes,
  links,
  selectedPokemon,
  onPokemonSelect,
  onPokemonClick,
  onPokemonHover,
  similarPokemon = [],
  similarityById = {},
  selectedNode,
  pokemonDetailsById = {},
  tutorialStep = null,
  tutorialSelectedStarter = null,
}) => {
  const OVERVIEW_MAX_LINKS_PER_NODE = 5;
  const OVERVIEW_MIN_LINK_SIMILARITY = 0.42;
  const SELECTED_SPIRAL_ANGLE = Math.PI * (3 - Math.sqrt(5));
  const SELECTED_SPIRAL_PITCH = 2.6;
  const svgRef = useRef();
  const simulationRef = useRef();
  const wrapperRef = useRef();
  const [tooltip, setTooltip] = useState(null);
  const [clusterTooltip, setClusterTooltip] = useState(null);

  const getNodeTypeFill = useCallback((node) => {
    const [typeA, typeB] = (node.types || []).filter(Boolean);
    const colorA = TYPE_COLORS[typeA] || "#7ec8e3";
    const colorB = TYPE_COLORS[typeB] || colorA;

    if (!typeA) {
      return { fill: "#7ec8e3", gradient: null };
    }

    if (!typeB || typeB === typeA) {
      return { fill: colorA, gradient: null };
    }

    return {
      fill: `url(#pokemon-type-gradient-${node.pokemon_id})`,
      gradient: [colorA, colorB],
    };
  }, []);

  const getNodeTypeColors = useCallback((node) => {
    const [typeA, typeB] = (node.types || []).filter(Boolean);
    const colorA = TYPE_COLORS[typeA] || "#7ec8e3";
    const colorB = TYPE_COLORS[typeB] || colorA;

    if (!typeA) {
      return ["#7ec8e3", "#7ec8e3"];
    }

    if (!typeB || typeB === typeA) {
      return [colorA, colorA];
    }

    return [colorA, colorB];
  }, []);

  const selectedNodeColors = useMemo(() => {
    if (!selectedPokemon) {
      return ["#7ec8e3", "#7ec8e3"];
    }

    const selectedSourceNode =
      selectedNode || nodes.find((node) => node.pokemon_id === selectedPokemon);

    if (!selectedSourceNode) {
      return ["#7ec8e3", "#7ec8e3"];
    }

    return getNodeTypeColors(selectedSourceNode);
  }, [getNodeTypeColors, nodes, selectedNode, selectedPokemon]);

  const similarityStats = useMemo(() => {
    const values = similarPokemon
      .map((pokemon) => pokemon.similarity)
      .filter((value) => typeof value === "number" && Number.isFinite(value));

    if (values.length === 0) {
      return { min: 0, max: 1, span: 1 };
    }

    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = Math.max(max - min, 1e-6);

    return { min, max, span };
  }, [similarPokemon]);

  const getSimilarityScore = useCallback(
    (node) => {
      if (node.pokemon_id === selectedPokemon) {
        return 1;
      }

      const raw = similarityById[node.pokemon_id];
      if (typeof raw !== "number" || !Number.isFinite(raw)) {
        return 0;
      }

      return Math.max(0, Math.min(1, raw));
    },
    [selectedPokemon, similarityById],
  );

  const focusedNodes = useMemo(() => {
    if (!selectedPokemon || !selectedNode || similarPokemon.length === 0) {
      return nodes.slice(0, 400);
    }

    const byId = new Map(nodes.map((node) => [node.pokemon_id, node]));
    const center = byId.get(selectedPokemon) || selectedNode;

    // Only include neighbors that are present in `nodes` (= filteredNodes from App).
    // similarPokemon is sorted by similarity descending.
    const neighbors = similarPokemon
      .filter((p) => p.id !== selectedPokemon)
      .map((p) => byId.get(p.id))
      .filter(Boolean);

    return [center, ...neighbors];
  }, [nodes, selectedPokemon, selectedNode, similarPokemon]);

  const focusedLinks = useMemo(() => {
    const pokemonIdByNodeIndex = new Map(
      nodes.map((node) => [node.id, node.pokemon_id]),
    );

    if (!selectedPokemon || similarPokemon.length === 0) {
      // Only keep links where BOTH endpoints are actually in focusedNodes.
      // With 1025 Pokémon, focusedNodes is capped at 220, so many link
      // targets would be missing from the simulation — D3 throws "node not found".
      const focusedPokemonIdSet = new Set(
        focusedNodes.map((n) => n.pokemon_id),
      );

      const rawLinks = links
        .map((link) => {
          const source =
            typeof link.source === "object" ? link.source.id : link.source;
          const target =
            typeof link.target === "object" ? link.target.id : link.target;

          return {
            source: pokemonIdByNodeIndex.get(source),
            target: pokemonIdByNodeIndex.get(target),
            similarity: link.similarity,
          };
        })
        .filter(
          (link) =>
            link.source != null &&
            link.target != null &&
            focusedPokemonIdSet.has(link.source) &&
            focusedPokemonIdSet.has(link.target),
        );

      const sortedLinks = rawLinks
        .filter(
          (link) => (link.similarity || 0) >= OVERVIEW_MIN_LINK_SIMILARITY,
        )
        .sort((a, b) => (b.similarity || 0) - (a.similarity || 0));

      const degreeByPokemonId = new Map();
      const keptLinks = [];

      sortedLinks.forEach((link) => {
        const sourceDegree = degreeByPokemonId.get(link.source) || 0;
        const targetDegree = degreeByPokemonId.get(link.target) || 0;

        if (
          sourceDegree >= OVERVIEW_MAX_LINKS_PER_NODE ||
          targetDegree >= OVERVIEW_MAX_LINKS_PER_NODE
        ) {
          return;
        }

        keptLinks.push(link);
        degreeByPokemonId.set(link.source, sourceDegree + 1);
        degreeByPokemonId.set(link.target, targetDegree + 1);
      });

      return keptLinks;
    }

    const focusedPokemonIds = new Set(
      focusedNodes.map((node) => node.pokemon_id),
    );

    return similarPokemon
      .filter(
        (pokemon) =>
          pokemon.id !== selectedPokemon &&
          focusedPokemonIds.has(pokemon.id) &&
          focusedPokemonIds.has(selectedPokemon),
      )
      .map((pokemon) => ({
        source: selectedPokemon,
        target: pokemon.id,
        similarity: pokemon.similarity,
      }));
  }, [nodes, links, selectedPokemon, similarPokemon, focusedNodes]);

  const getNodeRadius = useCallback(
    (node) => {
      if (!selectedPokemon) {
        return 8;
      }

      if (node.pokemon_id === selectedPokemon) {
        return 52;
      }

      const relativeSimilarity = getSimilarityScore(node);
      // Keep selected-view nodes compact so overlap handling does not inflate the whole layout.
      return 4 + relativeSimilarity * 12;
    },
    [selectedPokemon, getSimilarityScore],
  );

  const selectedSimilarityRange = useMemo(() => {
    if (!selectedPokemon) {
      return { min: 0, max: 1, span: 1 };
    }

    const visibleNeighborScores = focusedNodes
      .filter((node) => node.pokemon_id !== selectedPokemon)
      .map((node) => similarityById[node.pokemon_id])
      .filter((score) => typeof score === "number" && Number.isFinite(score));

    if (visibleNeighborScores.length === 0) {
      return { min: 0, max: 1, span: 1 };
    }

    const min = Math.min(...visibleNeighborScores);
    const max = Math.max(...visibleNeighborScores);
    return {
      min,
      max,
      span: Math.max(max - min, 1e-6),
    };
  }, [focusedNodes, selectedPokemon, similarityById]);

  const getRelativeSimilarityScore = useCallback(
    (node) => {
      if (node.pokemon_id === selectedPokemon) {
        return 1;
      }

      const rawSimilarity = getSimilarityScore(node);
      if (!selectedPokemon) {
        return rawSimilarity;
      }

      return Math.max(
        0,
        Math.min(
          1,
          (rawSimilarity - selectedSimilarityRange.min) /
            selectedSimilarityRange.span,
        ),
      );
    },
    [selectedPokemon, getSimilarityScore, selectedSimilarityRange],
  );

  const getTargetDistance = useCallback(
    (node) => {
      if (node.pokemon_id === selectedPokemon) {
        return 0;
      }

      if (!selectedPokemon) {
        return 0;
      }

      const similarity = getSimilarityScore(node);
      const relativeSimilarity = getRelativeSimilarityScore(node);
      const touchingDistance =
        getNodeRadius({ pokemon_id: selectedPokemon }) +
        getNodeRadius(node) +
        2;
      const absoluteDissimilarity = 1 - similarity;
      const relativeDissimilarity = 1 - relativeSimilarity;

      // Use both absolute and in-neighborhood dissimilarity so truly weak
      // matches can peel off into their own outer bands instead of collapsing
      // into one visually uniform ring.
      return (
        touchingDistance +
        Math.pow(absoluteDissimilarity, 2.15) * 280 +
        Math.pow(relativeDissimilarity, 1.55) * 190
      );
    },
    [
      selectedPokemon,
      getSimilarityScore,
      getRelativeSimilarityScore,
      getNodeRadius,
    ],
  );

  useEffect(() => {
    if (!focusedNodes || focusedNodes.length === 0) {
      return undefined;
    }

    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;
    const centerX = width / 2;
    const centerY = height / 2;
    const overviewPadding = 24;
    const overviewLabelGutter = selectedPokemon
      ? { top: 0, right: 0, bottom: 0, left: 0 }
      : { top: 44, right: 64, bottom: 98, left: 64 };
    const overviewLeft = overviewPadding + overviewLabelGutter.left;
    const overviewRight = width - overviewPadding - overviewLabelGutter.right;
    const overviewTop = overviewPadding + overviewLabelGutter.top;
    const overviewBottom =
      height - overviewPadding - overviewLabelGutter.bottom;
    const overviewCenterX = (overviewLeft + overviewRight) / 2;
    const overviewCenterY = (overviewTop + overviewBottom) / 2;
    // Keep sprite centers away from hard boundaries so edge clusters do not flatten.
    const overviewNodeInset = selectedPokemon ? 0 : 54;
    const overviewNodeLeft = overviewLeft + overviewNodeInset;
    const overviewNodeRight = overviewRight - overviewNodeInset;
    const overviewNodeTop = overviewTop + overviewNodeInset;
    const overviewNodeBottom = overviewBottom - overviewNodeInset;
    const overviewNodeWidth = Math.max(overviewNodeRight - overviewNodeLeft, 1);
    const overviewNodeHeight = Math.max(
      overviewNodeBottom - overviewNodeTop,
      1,
    );

    const overviewCoords = focusedNodes
      .map((node) => ({
        x:
          typeof node.overview_x === "number" &&
          Number.isFinite(node.overview_x)
            ? node.overview_x
            : null,
        y:
          typeof node.overview_y === "number" &&
          Number.isFinite(node.overview_y)
            ? node.overview_y
            : null,
      }))
      .filter((coord) => coord.x != null && coord.y != null);

    const overviewBounds =
      overviewCoords.length > 0
        ? {
            minX: Math.min(...overviewCoords.map((coord) => coord.x)),
            maxX: Math.max(...overviewCoords.map((coord) => coord.x)),
            minY: Math.min(...overviewCoords.map((coord) => coord.y)),
            maxY: Math.max(...overviewCoords.map((coord) => coord.y)),
          }
        : null;
    const overviewSpanX = Math.max(
      (overviewBounds?.maxX ?? 1) - (overviewBounds?.minX ?? -1),
      1e-6,
    );
    const overviewSpanY = Math.max(
      (overviewBounds?.maxY ?? 1) - (overviewBounds?.minY ?? -1),
      1e-6,
    );

    const neighborOrder = focusedNodes
      .filter((node) => node.pokemon_id !== selectedPokemon)
      .slice()
      .sort((a, b) => a.pokemon_id - b.pokemon_id);

    const neighborRank = new Map(
      neighborOrder.map((node, index) => [node.pokemon_id, index]),
    );

    const baseLayoutNodes = focusedNodes.map((node) => {
      const similarity = similarityById[node.pokemon_id] ?? null;
      const relativeSimilarity = getRelativeSimilarityScore(node);
      const radius = getNodeRadius(node);
      let angle = -Math.PI / 2;
      let spiralOffset = 0;

      if (node.pokemon_id !== selectedPokemon) {
        const rank = neighborRank.get(node.pokemon_id) ?? 0;
        angle = -Math.PI / 2 + rank * SELECTED_SPIRAL_ANGLE;
        // Gentle outward spiral: improves readability without globally inflating
        // the neighborhood or forcing a single node per angle.
        spiralOffset = SELECTED_SPIRAL_PITCH * Math.sqrt(rank);
      }

      const baseDistance = getTargetDistance(node) + spiralOffset;
      const overviewX =
        typeof node.overview_x === "number"
          ? overviewNodeLeft +
            ((node.overview_x - (overviewBounds?.minX ?? -1)) / overviewSpanX) *
              overviewNodeWidth
          : centerX;
      const overviewY =
        typeof node.overview_y === "number"
          ? overviewNodeTop +
            ((node.overview_y - (overviewBounds?.minY ?? -1)) / overviewSpanY) *
              overviewNodeHeight
          : centerY;

      return {
        ...node,
        similarity,
        relativeSimilarity,
        radius,
        angle,
        baseDistance,
        distance: baseDistance,
        anchorX: selectedPokemon
          ? centerX + Math.cos(angle) * baseDistance
          : overviewX,
        anchorY: selectedPokemon
          ? centerY + Math.sin(angle) * baseDistance
          : overviewY,
        tx: selectedPokemon
          ? centerX + Math.cos(angle) * baseDistance
          : overviewX,
        ty: selectedPokemon
          ? centerY + Math.sin(angle) * baseDistance
          : overviewY,
        x: selectedPokemon
          ? centerX + Math.cos(angle) * baseDistance
          : overviewX,
        y: selectedPokemon
          ? centerY + Math.sin(angle) * baseDistance
          : overviewY,
      };
    });

    let layoutNodes = baseLayoutNodes;

    if (selectedPokemon) {
      layoutNodes = baseLayoutNodes.map((node) => {
        if (node.pokemon_id === selectedPokemon) {
          return {
            ...node,
            distance: 0,
            tx: centerX,
            ty: centerY,
            x: centerX,
            y: centerY,
          };
        }

        const distance = node.baseDistance;
        const x = centerX + Math.cos(node.angle) * distance;
        const y = centerY + Math.sin(node.angle) * distance;

        return {
          ...node,
          distance,
          tx: x,
          ty: y,
          x,
          y,
        };
      });
    }

    const layoutLinks = focusedLinks.map((link) => ({ ...link }));

    const nodesByPokemonId = new Map(
      layoutNodes.map((node) => [node.pokemon_id, node]),
    );

    layoutLinks.forEach((link) => {
      link.source = nodesByPokemonId.get(link.source);
      link.target = nodesByPokemonId.get(link.target);
    });

    if (selectedPokemon) {
      const centerNode = nodesByPokemonId.get(selectedPokemon);
      if (centerNode) {
        centerNode.fx = centerX;
        centerNode.fy = centerY;
      }
    }

    d3.select(svgRef.current).selectAll("*").remove();

    const svg = d3
      .select(svgRef.current)
      .attr("width", width)
      .attr("height", height);

    const g = svg.append("g");

    if (!selectedPokemon) {
      const axisLayer = g.append("g").attr("class", "overview-axes");
      axisLayer
        .append("line")
        .attr("x1", overviewLeft)
        .attr("y1", overviewCenterY)
        .attr("x2", overviewRight)
        .attr("y2", overviewCenterY)
        .attr("stroke", "#aab0c4")
        .attr("stroke-width", 1.4)
        .attr("stroke-dasharray", "6 6")
        .attr("stroke-opacity", 0.7)
        .style("pointer-events", "none");

      axisLayer
        .append("line")
        .attr("x1", overviewCenterX)
        .attr("y1", overviewTop)
        .attr("x2", overviewCenterX)
        .attr("y2", overviewBottom)
        .attr("stroke", "#aab0c4")
        .attr("stroke-width", 1.4)
        .attr("stroke-dasharray", "6 6")
        .attr("stroke-opacity", 0.7)
        .style("pointer-events", "none");

      axisLayer
        .append("text")
        .attr("x", overviewLeft - 34)
        .attr("y", overviewCenterY - 8)
        .attr("fill", "#8a90a3")
        .attr("font-size", 13)
        .attr("font-weight", 600)
        .attr("letter-spacing", "0.03em")
        .attr("text-anchor", "end")
        .text("Buzz")
        .style("pointer-events", "none");

      axisLayer
        .append("text")
        .attr("x", overviewRight + 34)
        .attr("y", overviewCenterY - 8)
        .attr("fill", "#8a90a3")
        .attr("font-size", 13)
        .attr("font-weight", 600)
        .attr("letter-spacing", "0.03em")
        .text("Chirp")
        .style("pointer-events", "none");

      axisLayer
        .append("text")
        .attr("x", overviewCenterX)
        .attr("y", overviewTop - 24)
        .attr("fill", "#8a90a3")
        .attr("font-size", 13)
        .attr("font-weight", 600)
        .attr("letter-spacing", "0.03em")
        .attr("text-anchor", "middle")
        .text("Punchy")
        .style("pointer-events", "none");

      axisLayer
        .append("text")
        .attr("x", overviewCenterX)
        .attr("y", overviewBottom + 40)
        .attr("fill", "#8a90a3")
        .attr("font-size", 13)
        .attr("font-weight", 600)
        .attr("letter-spacing", "0.03em")
        .attr("text-anchor", "middle")
        .text("Sustained")
        .style("pointer-events", "none");
    }

    const defs = svg.append("defs");
    layoutNodes.forEach((node) => {
      const { gradient } = getNodeTypeFill(node);
      if (!gradient) {
        return;
      }

      const gradientId = `pokemon-type-gradient-${node.pokemon_id}`;
      const gradientEl = defs
        .append("linearGradient")
        .attr("id", gradientId)
        .attr("x1", "0%")
        .attr("y1", "0%")
        .attr("x2", "100%")
        .attr("y2", "0%");

      gradientEl
        .append("stop")
        .attr("offset", "0%")
        .attr("stop-color", gradient[0]);

      gradientEl
        .append("stop")
        .attr("offset", "50%")
        .attr("stop-color", gradient[0]);

      gradientEl
        .append("stop")
        .attr("offset", "50%")
        .attr("stop-color", gradient[1]);

      gradientEl
        .append("stop")
        .attr("offset", "100%")
        .attr("stop-color", gradient[1]);
    });

    let simulation;
    if (selectedPokemon) {
      // Selected mode is static: nodes stay exactly at the positions implied by
      // their individual similarity scores, with a light collision/radial pass
      // to reduce overlap without collapsing into a generic force blob.
      simulation = d3
        .forceSimulation(layoutNodes)
        .force(
          "radial",
          d3
            .forceRadial((node) => node.baseDistance, centerX, centerY)
            .strength(0.08),
        )
        .force("x", d3.forceX((node) => node.tx).strength(0.02))
        .force("y", d3.forceY((node) => node.ty).strength(0.02))
        .force(
          "collision",
          d3
            .forceCollide()
            .radius((node) => node.radius + 2)
            .strength(0.35),
        )
        .alphaDecay(0.16)
        .velocityDecay(0.7);
    } else {
      simulation = d3
        .forceSimulation(layoutNodes)
        .force("x", d3.forceX((node) => node.anchorX).strength(0.95))
        .force("y", d3.forceY((node) => node.anchorY).strength(0.95))
        .force(
          "collision",
          d3
            .forceCollide()
            .radius((node) => getNodeRadius(node) * 0.9 + 0.55)
            .strength(0.5),
        )
        .alphaDecay(0.12)
        .velocityDecay(0.78);
    }

    simulationRef.current = simulation;

    const link = g
      .append("g")
      .selectAll("line")
      .data(layoutLinks)
      .enter()
      .append("line")
      .attr("class", "link")
      .attr("stroke-width", (d) => {
        if (!selectedPokemon) {
          return 0.4;
        }

        const normalized = Math.pow(
          Math.max(
            0,
            Math.min(
              1,
              ((d.similarity || similarityStats.min) - similarityStats.min) /
                similarityStats.span,
            ),
          ),
          0.65,
        );

        return 0.4 + normalized * 1.2;
      })
      .attr("stroke-opacity", (d) => {
        if (!selectedPokemon) {
          return 0.03;
        }

        const normalized = Math.pow(
          Math.max(
            0,
            Math.min(
              1,
              ((d.similarity || similarityStats.min) - similarityStats.min) /
                similarityStats.span,
            ),
          ),
          0.65,
        );

        return 0.02 + normalized * 0.08;
      });

    if (selectedPokemon) {
      link.style("stroke", (d) => {
        const targetX = typeof d.target?.x === "number" ? d.target.x : centerX;
        return targetX < centerX
          ? selectedNodeColors[0]
          : selectedNodeColors[1];
      });
    }

    const clusterOutlineLayer = g.append("g").attr("class", "cluster-outlines");

    const getClusterOutlinePath = (cluster) => {
      const points = [];
      const padding = 15;
      const steps = 10;

      cluster.nodes.forEach((clusterNode) => {
        const radius = clusterNode.radius + padding;
        for (let step = 0; step < steps; step += 1) {
          const angle = (Math.PI * 2 * step) / steps;
          points.push([
            clusterNode.x + Math.cos(angle) * radius,
            clusterNode.y + Math.sin(angle) * radius,
          ]);
        }
      });

      const hull = d3.polygonHull(points);
      if (!hull || hull.length < 3) {
        return null;
      }

      return d3.line().curve(d3.curveCardinalClosed.tension(0.72))(hull);
    };

    let clusterOutline = null;
    let clusterHitArea = null;
    let overviewClusters = [];

    if (!selectedPokemon) {
      const clustersById = new Map();
      layoutNodes.forEach((layoutNode) => {
        if (layoutNode.cluster_id == null) {
          return;
        }

        if (!clustersById.has(layoutNode.cluster_id)) {
          clustersById.set(layoutNode.cluster_id, []);
        }
        clustersById.get(layoutNode.cluster_id).push(layoutNode);
      });

      overviewClusters = Array.from(
        clustersById,
        ([clusterId, clusterNodes]) => {
          const representative =
            clusterNodes.find(
              (clusterNode) =>
                clusterNode.pokemon_id ===
                clusterNodes[0].cluster_representative_id,
            ) ||
            clusterNodes
              .slice()
              .sort(
                (a, b) =>
                  (b.representativeness || 0) - (a.representativeness || 0),
              )[0];
          const scores = clusterNodes
            .map((clusterNode) => clusterNode.representativeness)
            .filter((score) => typeof score === "number");

          return {
            id: clusterId,
            nodes: clusterNodes,
            size: clusterNodes.length,
            representative,
            averageRepresentativeness:
              scores.length > 0
                ? scores.reduce((sum, score) => sum + score, 0) / scores.length
                : null,
          };
        },
      );

      const clusterGroup = clusterOutlineLayer
        .selectAll("g")
        .data(overviewClusters)
        .enter()
        .append("g")
        .attr("class", "cluster-outline-group");

      clusterOutline = clusterGroup
        .append("path")
        .attr("class", "cluster-outline")
        .attr("fill", "none");

      clusterHitArea = clusterGroup
        .append("path")
        .attr("class", "cluster-outline-hit-area")
        .attr("fill", "none")
        .on("mouseenter", (event, cluster) => {
          const bounds = wrapperRef.current?.getBoundingClientRect();
          if (!bounds) {
            return;
          }

          setClusterTooltip({
            x: event.clientX - bounds.left + 14,
            y: event.clientY - bounds.top - 12,
            size: cluster.size,
            representativeName: cluster.representative?.name,
            representativeId: cluster.representative?.pokemon_id,
            averageRepresentativeness: cluster.averageRepresentativeness,
          });
        })
        .on("mousemove", (event) => {
          const bounds = wrapperRef.current?.getBoundingClientRect();
          if (!bounds) {
            return;
          }

          setClusterTooltip((previous) =>
            previous
              ? {
                  ...previous,
                  x: event.clientX - bounds.left + 14,
                  y: event.clientY - bounds.top - 12,
                }
              : previous,
          );
        })
        .on("mouseleave", () => {
          setClusterTooltip(null);
        });
    }

    const node = g
      .append("g")
      .selectAll("g")
      .data(layoutNodes)
      .enter()
      .append("g")
      .attr("class", "node")
      .style("opacity", (d) =>
        tutorialStep === 2 &&
        tutorialSelectedStarter &&
        d.pokemon_id !== tutorialSelectedStarter
          ? 0.28
          : 1,
      )
      .style("cursor", (d) =>
        tutorialStep === 2 &&
        tutorialSelectedStarter &&
        d.pokemon_id !== tutorialSelectedStarter
          ? "not-allowed"
          : "pointer",
      );

    node
      .append("circle")
      .attr("r", (d) => d.radius + 3)
      .attr("fill", (d) => getNodeTypeFill(d).fill)
      .attr("fill-opacity", 0.18)
      .attr("stroke", (d) =>
        d.pokemon_id === selectedPokemon ? "#ffffff" : "none",
      )
      .attr("stroke-width", (d) => (d.pokemon_id === selectedPokemon ? 3 : 0));

    node
      .append("image")
      .attr("class", "node-sprite")
      .attr("x", (d) => -d.radius)
      .attr("y", (d) => -d.radius)
      .attr("width", (d) => d.radius * 2)
      .attr("height", (d) => d.radius * 2)
      .attr("href", (d) => d.sprite_url || "")
      .attr("opacity", 0.96)
      .style("pointer-events", "none");

    if (tutorialStep === 2 && tutorialSelectedStarter) {
      node
        .filter((d) => d.pokemon_id === tutorialSelectedStarter)
        .raise()
        .append("circle")
        .attr("class", "tutorial-node-highlight-halo")
        .attr("r", (d) => d.radius + 5)
        .attr("fill", "none")
        .attr("stroke", "#ffd700")
        .attr("stroke-width", 7)
        .attr("vector-effect", "non-scaling-stroke")
        .style("pointer-events", "none");

      node
        .filter((d) => d.pokemon_id === tutorialSelectedStarter)
        .raise()
        .append("circle")
        .attr("class", "tutorial-node-highlight")
        .attr("r", (d) => d.radius + 5)
        .attr("fill", "none")
        .attr("stroke", "#ffd700")
        .attr("stroke-width", 3)
        .attr("vector-effect", "non-scaling-stroke")
        .style("pointer-events", "none");
    }

    node.on("mouseenter", (event, d) => {
      const bounds = wrapperRef.current?.getBoundingClientRect();
      if (!bounds) {
        return;
      }

      if (onPokemonHover) {
        onPokemonHover(d.pokemon_id);
      }

      const details = pokemonDetailsById[d.pokemon_id] || {};
      setTooltip({
        x: event.clientX - bounds.left + 14,
        y: event.clientY - bounds.top - 12,
        name: d.name,
        id: d.pokemon_id,
        similarity: d.similarity,
        relativeSimilarity: d.relativeSimilarity,
        representativeness: d.representativeness,
        types: details.types || d.types || [],
        generation: details.generation || d.generation,
        habitat: details.habitat,
        description: details.description,
      });
    });

    node.on("mousemove", (event) => {
      const bounds = wrapperRef.current?.getBoundingClientRect();
      if (!bounds) {
        return;
      }

      setTooltip((previous) => {
        if (!previous) {
          return previous;
        }

        return {
          ...previous,
          x: event.clientX - bounds.left + 14,
          y: event.clientY - bounds.top - 12,
        };
      });
    });

    node.on("mouseleave", () => {
      setTooltip(null);
    });

    node.on("click", (event, d) => {
      event.stopPropagation();
      if (
        tutorialStep === 2 &&
        tutorialSelectedStarter &&
        d.pokemon_id !== tutorialSelectedStarter
      ) {
        return;
      }
      if (onPokemonClick) {
        onPokemonClick(d.pokemon_id);
      }
    });

    node.on("dblclick", (event, d) => {
      event.stopPropagation();
      if (
        tutorialStep === 2 &&
        tutorialSelectedStarter &&
        d.pokemon_id !== tutorialSelectedStarter
      ) {
        return;
      }
      onPokemonSelect(d.pokemon_id);
    });

    svg.on("click", () => {
      setTooltip(null);
      setClusterTooltip(null);
    });

    // Pre-settle silently before rendering.
    simulation.tick(selectedPokemon ? 35 : 180);
    simulation.stop();

    if (selectedPokemon) {
      const rankedNeighbors = layoutNodes
        .filter((node) => node.pokemon_id !== selectedPokemon)
        .slice()
        .sort((a, b) => {
          const similarityDelta = (b.similarity || 0) - (a.similarity || 0);
          if (Math.abs(similarityDelta) > 1e-9) {
            return similarityDelta;
          }
          return a.pokemon_id - b.pokemon_id;
        });

      let minAllowedDistance = 0;
      rankedNeighbors.forEach((node) => {
        const dx = node.x - centerX;
        const dy = node.y - centerY;
        const actualDistance = Math.hypot(dx, dy);
        const correctedDistance = Math.max(
          actualDistance,
          node.baseDistance,
          minAllowedDistance,
        );
        const scale = correctedDistance / Math.max(actualDistance, 1e-6);

        node.x = centerX + dx * scale;
        node.y = centerY + dy * scale;
        node.tx = node.x;
        node.ty = node.y;
        node.distance = correctedDistance;

        minAllowedDistance = correctedDistance;
      });

      const orderedNeighbors = rankedNeighbors.slice();
      for (let index = 0; index < orderedNeighbors.length; index += 1) {
        const node = orderedNeighbors[index];
        let distance = node.distance;
        let moved = true;
        let safety = 0;

        while (moved && safety < 120) {
          moved = false;
          safety += 1;

          const blockers = [
            layoutNodes.find(
              (candidate) => candidate.pokemon_id === selectedPokemon,
            ),
          ]
            .concat(orderedNeighbors.slice(0, index))
            .filter(Boolean);

          for (const other of blockers) {
            const otherDx = other.x - centerX;
            const otherDy = other.y - centerY;
            const candidateX = centerX + Math.cos(node.angle) * distance;
            const candidateY = centerY + Math.sin(node.angle) * distance;
            const dx = candidateX - (centerX + otherDx);
            const dy = candidateY - (centerY + otherDy);
            const minSeparation = node.radius + other.radius + 3;

            if (Math.hypot(dx, dy) < minSeparation) {
              distance += Math.max(1.5, minSeparation - Math.hypot(dx, dy));
              moved = true;
            }
          }
        }

        node.distance = distance;
        node.x = centerX + Math.cos(node.angle) * distance;
        node.y = centerY + Math.sin(node.angle) * distance;
        node.tx = node.x;
        node.ty = node.y;
      }
    } else {
      for (let pass = 0; pass < 6; pass += 1) {
        let moved = false;

        for (let i = 0; i < layoutNodes.length; i += 1) {
          const a = layoutNodes[i];
          for (let j = i + 1; j < layoutNodes.length; j += 1) {
            const b = layoutNodes[j];
            let dx = b.x - a.x;
            let dy = b.y - a.y;
            let distance = Math.hypot(dx, dy);
            const visibleRadiusA = a.radius + 3;
            const visibleRadiusB = b.radius + 3;
            const minSeparation = visibleRadiusA + visibleRadiusB + 1.25;

            if (distance >= minSeparation) {
              continue;
            }

            moved = true;
            if (distance < 1e-6) {
              dx = j % 2 === 0 ? 1 : -1;
              dy = i % 2 === 0 ? 1 : -1;
              distance = Math.hypot(dx, dy);
            }

            const push = (minSeparation - distance) / 2;
            const nx = dx / distance;
            const ny = dy / distance;

            a.x -= nx * push;
            a.y -= ny * push;
            b.x += nx * push;
            b.y += ny * push;
          }
        }

        layoutNodes.forEach((node) => {
          node.x = node.anchorX + (node.x - node.anchorX) * 0.92;
          node.y = node.anchorY + (node.y - node.anchorY) * 0.92;
          node.tx = node.x;
          node.ty = node.y;
        });

        if (!moved) {
          break;
        }
      }

      const nodesByClusterId = new Map();
      layoutNodes.forEach((layoutNode) => {
        if (layoutNode.cluster_id == null) {
          return;
        }
        if (!nodesByClusterId.has(layoutNode.cluster_id)) {
          nodesByClusterId.set(layoutNode.cluster_id, []);
        }
        nodesByClusterId.get(layoutNode.cluster_id).push(layoutNode);
      });

      const clusterGroups = Array.from(nodesByClusterId.values()).filter(
        (clusterNodes) => clusterNodes.length > 0,
      );

      const measureCluster = (clusterNodes) => {
        const centerX =
          clusterNodes.reduce((sum, node) => sum + node.x, 0) /
          clusterNodes.length;
        const centerY =
          clusterNodes.reduce((sum, node) => sum + node.y, 0) /
          clusterNodes.length;
        let radius = 0;
        let minX = Infinity;
        let maxX = -Infinity;
        let minY = Infinity;
        let maxY = -Infinity;

        clusterNodes.forEach((node) => {
          const dx = node.x - centerX;
          const dy = node.y - centerY;
          radius = Math.max(radius, Math.hypot(dx, dy) + node.radius);
          minX = Math.min(minX, node.x - node.radius);
          maxX = Math.max(maxX, node.x + node.radius);
          minY = Math.min(minY, node.y - node.radius);
          maxY = Math.max(maxY, node.y + node.radius);
        });

        return {
          centerX,
          centerY,
          radius: radius + 12,
          minX,
          maxX,
          minY,
          maxY,
        };
      };

      if (clusterGroups.length > 1) {
        for (let pass = 0; pass < 220; pass += 1) {
          const metrics = clusterGroups.map((clusterNodes) =>
            measureCluster(clusterNodes),
          );
          let moved = false;

          for (let i = 0; i < clusterGroups.length; i += 1) {
            for (let j = i + 1; j < clusterGroups.length; j += 1) {
              const a = metrics[i];
              const b = metrics[j];
              let dx = b.centerX - a.centerX;
              let dy = b.centerY - a.centerY;
              let distance = Math.hypot(dx, dy);
              const minSeparation = a.radius + b.radius + 26;

              if (distance >= minSeparation) {
                continue;
              }

              if (distance < 1e-6) {
                dx = (i + 1) * 0.37;
                dy = (j + 1) * 0.61;
                distance = Math.hypot(dx, dy);
              }

              const overlap = (minSeparation - distance) / 2;
              const nx = dx / distance;
              const ny = dy / distance;

              clusterGroups[i].forEach((node) => {
                node.x -= nx * overlap;
                node.y -= ny * overlap;
              });
              clusterGroups[j].forEach((node) => {
                node.x += nx * overlap;
                node.y += ny * overlap;
              });
              moved = true;
            }
          }

          clusterGroups.forEach((clusterNodes) => {
            // Intentionally do not clamp clusters to the viewport; let edge
            // clusters keep their natural shape instead of flattening inward.
          });

          if (!moved) {
            break;
          }
        }

        clusterGroups.forEach((clusterNodes) => {
          clusterNodes.forEach((node) => {
            node.tx = node.x;
            node.ty = node.y;
          });
        });
      }

      clusterGroups.forEach((clusterNodes) => {
        if (clusterNodes.length < 6) {
          return;
        }

        const densityBoost = Math.min(0.9, clusterNodes.length / 48);
        const localGap = -0.45 - densityBoost * 0.15;

        for (
          let pass = 0;
          pass < 9 + Math.ceil(clusterNodes.length / 12);
          pass += 1
        ) {
          let moved = false;

          for (let i = 0; i < clusterNodes.length; i += 1) {
            const a = clusterNodes[i];
            for (let j = i + 1; j < clusterNodes.length; j += 1) {
              const b = clusterNodes[j];
              let dx = b.x - a.x;
              let dy = b.y - a.y;
              let distance = Math.hypot(dx, dy);
              const visibleRadiusA = a.radius + 3;
              const visibleRadiusB = b.radius + 3;
              const minSeparation = visibleRadiusA + visibleRadiusB + localGap;

              if (distance >= minSeparation) {
                continue;
              }

              moved = true;
              if (distance < 1e-6) {
                dx = j % 2 === 0 ? 1 : -1;
                dy = i % 2 === 0 ? 1 : -1;
                distance = Math.hypot(dx, dy);
              }

              const push = (minSeparation - distance) / 2;
              const nx = dx / distance;
              const ny = dy / distance;

              a.x -= nx * push;
              a.y -= ny * push;
              b.x += nx * push;
              b.y += ny * push;
            }
          }

          if (!moved) {
            break;
          }
        }
      });

      // One final local repack so clusters that were moved apart stay readable.
      // This is intentionally looser than the initial pass, but it catches the
      // rare dense-pair overlaps that show up in big clusters.
      for (let pass = 0; pass < 3; pass += 1) {
        let moved = false;

        for (let i = 0; i < layoutNodes.length; i += 1) {
          const a = layoutNodes[i];
          for (let j = i + 1; j < layoutNodes.length; j += 1) {
            const b = layoutNodes[j];
            let dx = b.x - a.x;
            let dy = b.y - a.y;
            let distance = Math.hypot(dx, dy);
            const visibleRadiusA = a.radius + 3;
            const visibleRadiusB = b.radius + 3;
            const minSeparation = visibleRadiusA + visibleRadiusB - 0.35;

            if (distance >= minSeparation) {
              continue;
            }

            moved = true;
            if (distance < 1e-6) {
              dx = j % 2 === 0 ? 1 : -1;
              dy = i % 2 === 0 ? 1 : -1;
              distance = Math.hypot(dx, dy);
            }

            const push = (minSeparation - distance) / 2;
            const nx = dx / distance;
            const ny = dy / distance;

            a.x -= nx * push;
            a.y -= ny * push;
            b.x += nx * push;
            b.y += ny * push;
          }
        }

        if (!moved) {
          break;
        }
      }
    }

    // Render the already-settled initial positions.
    const updateClusterOutlines = () => {
      if (!clusterOutline || !clusterHitArea) {
        return;
      }

      clusterOutline.attr("d", getClusterOutlinePath);
      clusterHitArea.attr("d", getClusterOutlinePath);
    };

    updateClusterOutlines();

    link
      .attr("x1", (d) => d.source.x)
      .attr("y1", (d) => d.source.y)
      .attr("x2", (d) => d.target.x)
      .attr("y2", (d) => d.target.y);
    node.attr("transform", (d) => `translate(${d.x},${d.y})`);

    // Update DOM positions during simulation runs.
    simulation.on("tick", () => {
      link
        .attr("x1", (d) => d.source.x)
        .attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x)
        .attr("y2", (d) => d.target.y);
      updateClusterOutlines();
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    const zoom = d3
      .zoom()
      .scaleExtent([0.15, 6])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
      });

    svg.call(zoom);
    if (selectedPokemon) {
      const centerRadius = getNodeRadius({ pokemon_id: selectedPokemon });
      const nonCenterNodes = layoutNodes.filter(
        (node) => node.pokemon_id !== selectedPokemon,
      );
      const maxExtent = nonCenterNodes.reduce((extent, node) => {
        const dx = Math.abs(node.x - centerX) + node.radius + 24;
        const dy = Math.abs(node.y - centerY) + node.radius + 24;
        return Math.max(extent, dx, dy);
      }, centerRadius + 24);
      const fitScale = Math.min(width, height) / Math.max(maxExtent * 2, 1);
      svg.call(
        zoom.transform,
        d3.zoomIdentity
          .translate(width / 2, height / 2)
          .scale(Math.max(0.15, Math.min(1.05, fitScale)))
          .translate(-centerX, -centerY),
      );
    } else if (tutorialStep === 2 && tutorialSelectedStarter) {
      const tutorialNode = layoutNodes.find(
        (node) => node.pokemon_id === tutorialSelectedStarter,
      );
      if (tutorialNode) {
        const zoomScale = 2.5;
        const tutorialTransform = d3.zoomIdentity
          .translate(width / 2, height / 2)
          .scale(zoomScale)
          .translate(-tutorialNode.x, -tutorialNode.y);

        svg.call(zoom.transform, d3.zoomIdentity);
        svg
          .transition()
          .delay(250)
          .duration(950)
          .ease(d3.easeCubicInOut)
          .call(zoom.transform, tutorialTransform);
      }
    }

    return () => {
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    focusedNodes,
    focusedLinks,
    selectedPokemon,
    similarityStats,
    getNodeRadius,
    getTargetDistance,
    getSimilarityScore,
    tutorialStep,
    tutorialSelectedStarter,
  ]);

  useEffect(() => {
    if (!tooltip) {
      return;
    }

    const details = pokemonDetailsById[tooltip.id];
    if (!details) {
      return;
    }

    setTooltip((previous) => {
      if (!previous || previous.id !== tooltip.id) {
        return previous;
      }

      return {
        ...previous,
        types: details.types || previous.types || [],
        generation: details.generation || previous.generation,
        habitat: details.habitat,
        description: details.description,
      };
    });
  }, [tooltip, pokemonDetailsById]);

  return (
    <div className="graph-root" ref={wrapperRef}>
      <svg ref={svgRef} style={{ width: "100%", height: "100%" }} />
      {tooltip ? (
        <div
          className="graph-tooltip"
          style={{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }}
        >
          <div className="graph-tooltip-name">{titleCase(tooltip.name)}</div>
          <div className="graph-tooltip-meta">#{tooltip.id}</div>
          {selectedPokemon &&
          tooltip.id !== selectedPokemon &&
          typeof tooltip.similarity === "number" ? (
            <div className="graph-tooltip-meta">
              Similarity: {(tooltip.similarity * 100).toFixed(1)}%
            </div>
          ) : null}
          {selectedPokemon &&
          tooltip.id !== selectedPokemon &&
          typeof tooltip.relativeSimilarity === "number" ? (
            <div className="graph-tooltip-meta">
              Relative Similarity:{" "}
              {(tooltip.relativeSimilarity * 100).toFixed(1)}%
            </div>
          ) : null}
          {!selectedPokemon &&
          typeof tooltip.representativeness === "number" ? (
            <div className="graph-tooltip-meta">
              Cluster Representativeness{" "}
              {(tooltip.representativeness * 100).toFixed(1)}%
            </div>
          ) : null}
          {tooltip.types && tooltip.types.length > 0 ? (
            <div className="graph-tooltip-meta">
              Types: {tooltip.types.map(titleCase).join(", ")}
            </div>
          ) : null}
          {tooltip.generation ? (
            <div className="graph-tooltip-meta">
              Generation: {formatGeneration(tooltip.generation)}
            </div>
          ) : null}
          {tooltip.habitat ? (
            <div className="graph-tooltip-meta">
              Habitat: {titleCase(tooltip.habitat)}
            </div>
          ) : null}
          {tooltip.description ? (
            <div className="graph-tooltip-meta">
              {formatDescription(tooltip.description)}
            </div>
          ) : null}
        </div>
      ) : null}
      {clusterTooltip ? (
        <div
          className="graph-tooltip graph-cluster-tooltip"
          style={{
            left: `${clusterTooltip.x}px`,
            top: `${clusterTooltip.y}px`,
          }}
        >
          <div className="graph-tooltip-name">Cluster</div>
          <div className="graph-tooltip-meta">
            Pokemon: {clusterTooltip.size}
          </div>
          {clusterTooltip.size > 2 && clusterTooltip.representativeName ? (
            <div className="graph-tooltip-meta">
              Most Representative:{" "}
              {titleCase(clusterTooltip.representativeName)}
              {clusterTooltip.representativeId
                ? ` #${clusterTooltip.representativeId}`
                : ""}
            </div>
          ) : null}
          {typeof clusterTooltip.averageRepresentativeness === "number" ? (
            <div className="graph-tooltip-meta">
              Avg. Representativeness:{" "}
              {(clusterTooltip.averageRepresentativeness * 100).toFixed(1)}%
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="graph-hint">
        {selectedPokemon
          ? "Double-click a Pokémon to center its audio neighborhood. Click to hear its cry."
          : "Overview map: clusters are positioned by cry character. Double-click a Pokémon to focus it."}
      </div>
    </div>
  );
};
