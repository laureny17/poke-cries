import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';
import { TYPE_COLORS } from '../typeColors';

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
}) => {
  const MAX_SELECTED_NEIGHBORS = 150;
  const OVERVIEW_MAX_LINKS_PER_NODE = 5;
  const OVERVIEW_MIN_LINK_SIMILARITY = 0.42;
  const SELECTED_SPIRAL_ANGLE = Math.PI * (3 - Math.sqrt(5));
  const SELECTED_SPIRAL_PITCH = 2.6;
  const svgRef = useRef();
  const simulationRef = useRef();
  const wrapperRef = useRef();
  const [tooltip, setTooltip] = useState(null);

  const getNodeTypeFill = useCallback(node => {
    const [typeA, typeB] = (node.types || []).filter(Boolean);
    const colorA = TYPE_COLORS[typeA] || '#7ec8e3';
    const colorB = TYPE_COLORS[typeB] || colorA;

    if (!typeA) {
      return { fill: '#7ec8e3', gradient: null };
    }

    if (!typeB || typeB === typeA) {
      return { fill: colorA, gradient: null };
    }

    return {
      fill: `url(#pokemon-type-gradient-${node.pokemon_id})`,
      gradient: [colorA, colorB],
    };
  }, []);

  const similarityStats = useMemo(() => {
    const values = similarPokemon
      .map(pokemon => pokemon.similarity)
      .filter(value => typeof value === 'number' && Number.isFinite(value));

    if (values.length === 0) {
      return { min: 0, max: 1, span: 1 };
    }

    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = Math.max(max - min, 1e-6);

    return { min, max, span };
  }, [similarPokemon]);

  const getSimilarityScore = useCallback(node => {
    if (node.pokemon_id === selectedPokemon) {
      return 1;
    }

    const raw = similarityById[node.pokemon_id];
    if (typeof raw !== 'number' || !Number.isFinite(raw)) {
      return 0;
    }

    return Math.max(0, Math.min(1, raw));
  }, [selectedPokemon, similarityById]);

  const focusedNodes = useMemo(() => {
    if (!selectedPokemon || !selectedNode || similarPokemon.length === 0) {
      return nodes.slice(0, 400);
    }

    const byId = new Map(nodes.map(node => [node.pokemon_id, node]));
    const center = byId.get(selectedPokemon) || selectedNode;

    // Only include neighbors that are present in `nodes` (= filteredNodes from App).
    // similarPokemon is sorted by similarity descending, so the slice naturally
    // gives the most-similar pokemon that pass the current gen/type filters.
    const neighbors = similarPokemon
      .filter(p => p.id !== selectedPokemon)
      .map(p => byId.get(p.id))
      .filter(Boolean)
      .slice(0, MAX_SELECTED_NEIGHBORS);

    return [center, ...neighbors];
  }, [nodes, selectedPokemon, selectedNode, similarPokemon]);

  const focusedLinks = useMemo(() => {
    const pokemonIdByNodeIndex = new Map(
      nodes.map(node => [node.id, node.pokemon_id])
    );

    if (!selectedPokemon || similarPokemon.length === 0) {
      // Only keep links where BOTH endpoints are actually in focusedNodes.
      // With 1025 Pokémon, focusedNodes is capped at 220, so many link
      // targets would be missing from the simulation — D3 throws "node not found".
      const focusedPokemonIdSet = new Set(focusedNodes.map(n => n.pokemon_id));

      const rawLinks = links
        .map(link => {
          const source = typeof link.source === 'object' ? link.source.id : link.source;
          const target = typeof link.target === 'object' ? link.target.id : link.target;

          return {
            source: pokemonIdByNodeIndex.get(source),
            target: pokemonIdByNodeIndex.get(target),
            similarity: link.similarity,
          };
        })
        .filter(link =>
          link.source != null && link.target != null &&
          focusedPokemonIdSet.has(link.source) &&
          focusedPokemonIdSet.has(link.target)
        );

      const sortedLinks = rawLinks
        .filter(link => (link.similarity || 0) >= OVERVIEW_MIN_LINK_SIMILARITY)
        .sort((a, b) => (b.similarity || 0) - (a.similarity || 0));

      const degreeByPokemonId = new Map();
      const keptLinks = [];

      sortedLinks.forEach(link => {
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
      focusedNodes.map(node => node.pokemon_id)
    );

    return similarPokemon
      .filter(
        pokemon =>
          pokemon.id !== selectedPokemon &&
          focusedPokemonIds.has(pokemon.id) &&
          focusedPokemonIds.has(selectedPokemon)
      )
      .map(pokemon => ({
        source: selectedPokemon,
        target: pokemon.id,
        similarity: pokemon.similarity,
      }));
  }, [nodes, links, selectedPokemon, similarPokemon, focusedNodes]);

  const getNodeRadius = useCallback(node => {
    if (!selectedPokemon) {
      return 8;
    }

    if (node.pokemon_id === selectedPokemon) {
      return 52;
    }

    const relativeSimilarity = getSimilarityScore(node);
    // Keep selected-view nodes compact so overlap handling does not inflate the whole layout.
    return 4 + (relativeSimilarity * 12);
  }, [selectedPokemon, getSimilarityScore]);

  const selectedSimilarityRange = useMemo(() => {
    if (!selectedPokemon) {
      return { min: 0, max: 1, span: 1 };
    }

    const visibleNeighborScores = focusedNodes
      .filter(node => node.pokemon_id !== selectedPokemon)
      .map(node => similarityById[node.pokemon_id])
      .filter(score => typeof score === 'number' && Number.isFinite(score));

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

  const getRelativeSimilarityScore = useCallback(node => {
    if (node.pokemon_id === selectedPokemon) {
      return 1;
    }

    const rawSimilarity = getSimilarityScore(node);
    if (!selectedPokemon) {
      return rawSimilarity;
    }

    return Math.max(
      0,
      Math.min(1, (rawSimilarity - selectedSimilarityRange.min) / selectedSimilarityRange.span)
    );
  }, [selectedPokemon, getSimilarityScore, selectedSimilarityRange]);

  const getTargetDistance = useCallback(node => {
    if (node.pokemon_id === selectedPokemon) {
      return 0;
    }

    if (!selectedPokemon) {
      return 0;
    }

    const relativeSimilarity = getRelativeSimilarityScore(node);
    const touchingDistance = getNodeRadius({ pokemon_id: selectedPokemon }) + getNodeRadius(node) + 2;

    // Best visible match (relative = 1) sits right next to the selected pokemon.
    return touchingDistance + (Math.pow(1 - relativeSimilarity, 1.75) * 130);
  }, [selectedPokemon, getRelativeSimilarityScore, getNodeRadius]);

  useEffect(() => {
    if (!focusedNodes || focusedNodes.length === 0) {
      return undefined;
    }

    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;
    const centerX = width / 2;
    const centerY = height / 2;
    const plotRadius = Math.min(width, height) * 0.42;

    const neighborOrder = focusedNodes
      .filter(node => node.pokemon_id !== selectedPokemon)
      .slice()
      .sort((a, b) => a.pokemon_id - b.pokemon_id);

    const neighborRank = new Map(
      neighborOrder.map((node, index) => [node.pokemon_id, index])
    );

    const baseLayoutNodes = focusedNodes.map(node => {
      const similarity = similarityById[node.pokemon_id] ?? null;
      const relativeSimilarity = getRelativeSimilarityScore(node);
      const radius = getNodeRadius(node);
      let angle = -Math.PI / 2;
      let spiralOffset = 0;

      if (node.pokemon_id !== selectedPokemon) {
        const rank = neighborRank.get(node.pokemon_id) ?? 0;
        angle = (-Math.PI / 2) + (rank * SELECTED_SPIRAL_ANGLE);
        // Gentle outward spiral: improves readability without globally inflating
        // the neighborhood or forcing a single node per angle.
        spiralOffset = SELECTED_SPIRAL_PITCH * Math.sqrt(rank);
      }

      const baseDistance = getTargetDistance(node) + spiralOffset;
      const overviewX = typeof node.overview_x === 'number'
        ? centerX + (node.overview_x * plotRadius)
        : centerX;
      const overviewY = typeof node.overview_y === 'number'
        ? centerY + (node.overview_y * plotRadius)
        : centerY;

      return {
        ...node,
        similarity,
        relativeSimilarity,
        radius,
        angle,
        baseDistance,
        distance: baseDistance,
        tx: selectedPokemon ? centerX + (Math.cos(angle) * baseDistance) : overviewX,
        ty: selectedPokemon ? centerY + (Math.sin(angle) * baseDistance) : overviewY,
        x: selectedPokemon ? centerX + (Math.cos(angle) * baseDistance) : overviewX,
        y: selectedPokemon ? centerY + (Math.sin(angle) * baseDistance) : overviewY,
      };
    });

    let layoutNodes = baseLayoutNodes;

    if (selectedPokemon) {
      layoutNodes = baseLayoutNodes.map(node => {
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
        const x = centerX + (Math.cos(node.angle) * distance);
        const y = centerY + (Math.sin(node.angle) * distance);

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

    const layoutLinks = focusedLinks.map(link => ({ ...link }));

    if (selectedPokemon) {
      const centerNode = layoutNodes.find(node => node.pokemon_id === selectedPokemon);
      if (centerNode) {
        centerNode.fx = centerX;
        centerNode.fy = centerY;
      }
    }

    d3.select(svgRef.current).selectAll('*').remove();

    const svg = d3.select(svgRef.current)
      .attr('width', width)
      .attr('height', height);

    const g = svg.append('g');

    const defs = svg.append('defs');
    layoutNodes.forEach(node => {
      const { gradient } = getNodeTypeFill(node);
      if (!gradient) {
        return;
      }

      const gradientId = `pokemon-type-gradient-${node.pokemon_id}`;
      const gradientEl = defs.append('linearGradient')
        .attr('id', gradientId)
        .attr('x1', '0%')
        .attr('y1', '0%')
        .attr('x2', '100%')
        .attr('y2', '0%');

      gradientEl.append('stop')
        .attr('offset', '0%')
        .attr('stop-color', gradient[0]);

      gradientEl.append('stop')
        .attr('offset', '50%')
        .attr('stop-color', gradient[0]);

      gradientEl.append('stop')
        .attr('offset', '50%')
        .attr('stop-color', gradient[1]);

      gradientEl.append('stop')
        .attr('offset', '100%')
        .attr('stop-color', gradient[1]);
    });

    let simulation;
    if (selectedPokemon) {
      const nodesByPokemonId = new Map(
        layoutNodes.map(node => [node.pokemon_id, node])
      );

      layoutLinks.forEach(link => {
        link.source = nodesByPokemonId.get(link.source);
        link.target = nodesByPokemonId.get(link.target);
      });

      // Selected mode is static: nodes stay exactly at the positions implied by
      // their individual similarity scores, with a light collision/radial pass
      // to reduce overlap without collapsing into a generic force blob.
      simulation = d3.forceSimulation(layoutNodes)
        .force('radial', d3.forceRadial(node => node.baseDistance, centerX, centerY).strength(0.08))
        .force('x', d3.forceX(node => node.tx).strength(0.02))
        .force('y', d3.forceY(node => node.ty).strength(0.02))
        .force(
          'collision',
          d3.forceCollide().radius(node => node.radius + 2).strength(0.35)
        )
        .alphaDecay(0.16)
        .velocityDecay(0.7);
    } else {
      simulation = d3.forceSimulation(layoutNodes)
        .force('x', d3.forceX(node => node.tx).strength(0.22))
        .force('y', d3.forceY(node => node.ty).strength(0.22))
        .force(
          'collision',
          d3.forceCollide().radius(node => getNodeRadius(node) + 3).strength(0.95)
        )
        .force('charge', d3.forceManyBody().strength(-8))
        .alphaDecay(0.06)
        .velocityDecay(0.45);
    }

    simulationRef.current = simulation;

    const link = g.append('g')
      .selectAll('line')
      .data(layoutLinks)
      .enter()
      .append('line')
      .attr('class', 'link')
      .attr('stroke-width', d => {
        if (!selectedPokemon) {
          return 0.4;
        }

        const normalized = Math.pow(
          Math.max(
            0,
            Math.min(1, ((d.similarity || similarityStats.min) - similarityStats.min) / similarityStats.span)
          ),
          0.65
        );

        return 0.4 + (normalized * 1.2);
      })
      .attr('stroke-opacity', d => {
        if (!selectedPokemon) {
          return 0.03;
        }

        const normalized = Math.pow(
          Math.max(
            0,
            Math.min(1, ((d.similarity || similarityStats.min) - similarityStats.min) / similarityStats.span)
          ),
          0.65
        );

        return 0.05 + (normalized * 0.22);
      });

    const node = g.append('g')
      .selectAll('g')
      .data(layoutNodes)
      .enter()
      .append('g')
      .attr('class', 'node');

    node.append('circle')
      .attr('r', d => d.radius + 3)
      .attr('fill', d => getNodeTypeFill(d).fill)
      .attr('fill-opacity', 0.18)
      .attr('stroke', d => (d.pokemon_id === selectedPokemon ? '#ffffff' : 'none'))
      .attr('stroke-width', d => (d.pokemon_id === selectedPokemon ? 3 : 0));

    node.append('image')
      .attr('class', 'node-sprite')
      .attr('x', d => -d.radius)
      .attr('y', d => -d.radius)
      .attr('width', d => d.radius * 2)
      .attr('height', d => d.radius * 2)
      .attr('href', d => d.sprite_url || '')
      .attr('opacity', 0.96)
      .style('pointer-events', 'none');

    node.on('mouseenter', (event, d) => {
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
        types: details.types || d.types || [],
        generation: details.generation || d.generation,
        habitat: details.habitat,
        description: details.description,
      });
    });

    node.on('mousemove', event => {
      const bounds = wrapperRef.current?.getBoundingClientRect();
      if (!bounds) {
        return;
      }

      setTooltip(previous => {
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

    node.on('mouseleave', () => {
      setTooltip(null);
    });

    node.on('click', (event, d) => {
      event.stopPropagation();
      if (onPokemonClick) {
        onPokemonClick(d.pokemon_id);
      }
    });

    node.on('dblclick', (event, d) => {
      event.stopPropagation();
      onPokemonSelect(d.pokemon_id);
    });

    svg.on('click', () => {
      setTooltip(null);
    });

    // Pre-settle silently before rendering.
    simulation.tick(selectedPokemon ? 35 : 180);
    simulation.stop();

    if (selectedPokemon) {
      const rankedNeighbors = layoutNodes
        .filter(node => node.pokemon_id !== selectedPokemon)
        .slice()
        .sort((a, b) => {
          const similarityDelta = (b.similarity || 0) - (a.similarity || 0);
          if (Math.abs(similarityDelta) > 1e-9) {
            return similarityDelta;
          }
          return a.pokemon_id - b.pokemon_id;
        });

      let minAllowedDistance = 0;
      rankedNeighbors.forEach(node => {
        const dx = node.x - centerX;
        const dy = node.y - centerY;
        const actualDistance = Math.hypot(dx, dy);
        const correctedDistance = Math.max(actualDistance, minAllowedDistance);
        const scale = correctedDistance / Math.max(actualDistance, 1e-6);

        node.x = centerX + (dx * scale);
        node.y = centerY + (dy * scale);
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

          const blockers = [layoutNodes.find(candidate => candidate.pokemon_id === selectedPokemon)]
            .concat(orderedNeighbors.slice(0, index))
            .filter(Boolean);

          for (const other of blockers) {
            const otherDx = other.x - centerX;
            const otherDy = other.y - centerY;
            const candidateX = centerX + (Math.cos(node.angle) * distance);
            const candidateY = centerY + (Math.sin(node.angle) * distance);
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
        node.x = centerX + (Math.cos(node.angle) * distance);
        node.y = centerY + (Math.sin(node.angle) * distance);
        node.tx = node.x;
        node.ty = node.y;
      }
    }

    // Render the already-settled initial positions.
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);
    node.attr('transform', d => `translate(${d.x},${d.y})`);

    // Update DOM positions during simulation runs.
    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);
      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    const zoom = d3.zoom()
      .scaleExtent([0.15, 6])
      .on('zoom', event => {
        g.attr('transform', event.transform);
      });

    svg.call(zoom);
    if (selectedPokemon) {
      const centerRadius = getNodeRadius({ pokemon_id: selectedPokemon });
      const nonCenterNodes = layoutNodes.filter(node => node.pokemon_id !== selectedPokemon);
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
          .translate(-centerX, -centerY)
      );
    }

    return () => {
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
    };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedNodes, focusedLinks, selectedPokemon, similarityStats, getNodeRadius, getTargetDistance, getSimilarityScore]);

  useEffect(() => {
    if (!tooltip) {
      return;
    }

    const details = pokemonDetailsById[tooltip.id];
    if (!details) {
      return;
    }

    setTooltip(previous => {
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
      <svg ref={svgRef} style={{ width: '100%', height: '100%' }} />
      {tooltip ? (
        <div
          className="graph-tooltip"
          style={{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }}
        >
          <div className="graph-tooltip-name">{tooltip.name}</div>
          <div className="graph-tooltip-meta">#{tooltip.id}</div>
          {typeof tooltip.similarity === 'number' ? (
            <div className="graph-tooltip-meta">
              Similarity {(tooltip.similarity * 100).toFixed(1)}%
            </div>
          ) : null}
          {typeof tooltip.relativeSimilarity === 'number' ? (
            <div className="graph-tooltip-meta">
              Relative {(tooltip.relativeSimilarity * 100).toFixed(1)}%
            </div>
          ) : null}
          {tooltip.types && tooltip.types.length > 0 ? (
            <div className="graph-tooltip-meta">Types: {tooltip.types.join(', ')}</div>
          ) : null}
          {tooltip.generation ? (
            <div className="graph-tooltip-meta">
              Generation: {String(tooltip.generation).replace('generation-', 'Gen ')}
            </div>
          ) : null}
          {tooltip.habitat ? (
            <div className="graph-tooltip-meta">Habitat: {tooltip.habitat}</div>
          ) : null}
          {tooltip.description ? (
            <div className="graph-tooltip-meta">{tooltip.description}</div>
          ) : null}
        </div>
      ) : null}
      <div className="graph-hint">
        Click a Pokémon to center its audio neighborhood.
      </div>
    </div>
  );
};
