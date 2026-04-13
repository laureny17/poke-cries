import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as d3 from 'd3';

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
  const svgRef = useRef();
  const simulationRef = useRef();
  const wrapperRef = useRef();
  const [tooltip, setTooltip] = useState(null);

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

  const getNormalizedSimilarity = useCallback(node => {
    if (node.pokemon_id === selectedPokemon) {
      return 1;
    }

    const raw = similarityById[node.pokemon_id];
    if (typeof raw !== 'number' || !Number.isFinite(raw)) {
      return 0;
    }

    const normalized = (raw - similarityStats.min) / similarityStats.span;

    // Emphasize midrange differences when raw scores are tightly clustered.
    return Math.pow(Math.max(0, Math.min(1, normalized)), 0.65);
  }, [selectedPokemon, similarityById, similarityStats]);

  const focusedNodes = useMemo(() => {
    if (!selectedPokemon || !selectedNode || similarPokemon.length === 0) {
      return nodes.slice(0, 400);
    }

    const byId = new Map(nodes.map(node => [node.pokemon_id, node]));
    const center = byId.get(selectedPokemon) || selectedNode;
    const neighbors = similarPokemon
      .map(p => byId.get(p.id) || {
        id: `sim-${p.id}`,
        pokemon_id: p.id,
        name: p.name,
        sprite_url: p.sprite_url,
      })
      .filter(Boolean);

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

      return links.slice(0, 4000)
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
    }

    const focusedPokemonIds = new Set(
      focusedNodes.map(node => node.pokemon_id)
    );

    return similarPokemon
      .filter(pokemon => focusedPokemonIds.has(pokemon.id) && focusedPokemonIds.has(selectedPokemon))
      .map(pokemon => ({
        source: selectedPokemon,
        target: pokemon.id,
        similarity: pokemon.similarity,
      }));
  }, [nodes, links, selectedPokemon, similarPokemon, focusedNodes]);

  const getNodeRadius = useCallback(node => {
    if (node.pokemon_id === selectedPokemon) {
      return 110;
    }

    const relativeSimilarity = getNormalizedSimilarity(node);
    // Range: 9 (least similar) → 55 (most similar). Max is exactly half of selected (110).
    return 9 + (relativeSimilarity * 46);
  }, [selectedPokemon, getNormalizedSimilarity]);

  const getTargetDistance = useCallback(node => {
    if (node.pokemon_id === selectedPokemon) {
      return 0;
    }

    const relativeSimilarity = getNormalizedSimilarity(node);
    // Exponential: very similar nodes cluster tightly near center,
    // dissimilar nodes spread dramatically far out.
    return 80 + (Math.pow(1 - relativeSimilarity, 1.5) * 540);
  }, [selectedPokemon, getNormalizedSimilarity]);

  const getStableAngle = useCallback(node => {
    const seedString = `${selectedPokemon || 0}:${node.pokemon_id}`;
    let hash = 0;
    for (let i = 0; i < seedString.length; i += 1) {
      hash = ((hash << 5) - hash + seedString.charCodeAt(i)) | 0;
    }

    const normalized = (Math.abs(hash) % 100000) / 100000;
    return normalized * Math.PI * 2;
  }, [selectedPokemon]);

  useEffect(() => {
    if (!focusedNodes || focusedNodes.length === 0) {
      return undefined;
    }

    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;
    const centerX = width / 2;
    const centerY = height / 2;

    const layoutNodes = focusedNodes.map(node => {
      const similarity = similarityById[node.pokemon_id] ?? null;
      const relativeSimilarity = getNormalizedSimilarity(node);
      const angle = getStableAngle(node);
      const radialDistance = getTargetDistance(node);

      return {
        ...node,
        similarity,
        relativeSimilarity,
        x: centerX + (Math.cos(angle) * radialDistance),
        y: centerY + (Math.sin(angle) * radialDistance),
      };
    });

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

    const linkForce = d3.forceLink(layoutLinks)
      .id(node => node.pokemon_id)
      .distance(link => {
        if (selectedPokemon) {
          const normalized = Math.pow(
            Math.max(
              0,
              Math.min(1, ((link.similarity || similarityStats.min) - similarityStats.min) / similarityStats.span)
            ),
            0.65
          );

          return 80 + (Math.pow(1 - normalized, 1.5) * 500);
        }
        return 100;
      })
      .strength(selectedPokemon ? 0.4 : 0.2);

    const simulation = d3.forceSimulation(layoutNodes)
      .force('link', linkForce)
      .force(
        'charge',
        d3.forceManyBody().strength(node => (node.pokemon_id === selectedPokemon ? -15 : -40))
      )
      .force('center', d3.forceCenter(centerX, centerY).strength(selectedPokemon ? 0.08 : 0.1))
      .force(
        'collision',
        d3.forceCollide().radius(node => getNodeRadius(node) + 4).strength(0.8)
      )
      .alphaDecay(0.12)
      .velocityDecay(0.8);

    if (selectedPokemon) {
      simulation.force(
        'radial',
        d3.forceRadial(node => getTargetDistance(node), centerX, centerY).strength(0.4)
      );
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
      .attr('class', 'node')
      .call(d3.drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended));

    node.append('circle')
      .attr('r', d => getNodeRadius(d) + 3)
      .attr('fill', d => (d.pokemon_id === selectedPokemon ? '#f9c74f' : '#7ec8e3'))
      .attr('fill-opacity', d => (d.pokemon_id === selectedPokemon ? 0.2 : 0.13));

    node.append('image')
      .attr('class', 'node-sprite')
      .attr('x', d => -getNodeRadius(d))
      .attr('y', d => -getNodeRadius(d))
      .attr('width', d => getNodeRadius(d) * 2)
      .attr('height', d => getNodeRadius(d) * 2)
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

    // Pre-settle the layout silently so nodes never visibly fly around on load.
    simulation.tick(200);
    simulation.stop();

    // Render the already-settled initial positions.
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);
    node.attr('transform', d => `translate(${d.x},${d.y})`);

    // Update DOM positions during drag-induced simulation runs.
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
      svg.call(zoom.transform, d3.zoomIdentity.translate(0, 0).scale(1.05));
    }

    function dragstarted(event, d) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    }

    function dragged(event, d) {
      d.fx = event.x;
      d.fy = event.y;
    }

    function dragended(event, d) {
      if (!event.active) simulation.alphaTarget(0);
      if (d.pokemon_id !== selectedPokemon) {
        d.fx = null;
        d.fy = null;
      }
    }

    return () => {
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
    };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedNodes, focusedLinks, selectedPokemon, similarityStats, getStableAngle, getNodeRadius, getTargetDistance]);

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
