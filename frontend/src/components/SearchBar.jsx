import React, { useState, useMemo, useRef, useEffect } from 'react';

export const SearchBar = ({ nodes, onSelect }) => {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef();

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return nodes
      .filter(n => n.name?.toLowerCase().includes(q))
      .sort((a, b) => {
        const aStart = a.name.toLowerCase().startsWith(q);
        const bStart = b.name.toLowerCase().startsWith(q);
        if (aStart && !bStart) return -1;
        if (!aStart && bStart) return 1;
        return a.pokemon_id - b.pokemon_id;
      })
      .slice(0, 8);
  }, [query, nodes]);

  useEffect(() => {
    const handler = e => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div className="search-root" ref={ref}>
      <input
        className="search-input"
        placeholder="SEARCH..."
        value={query}
        onChange={e => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
      />
      {open && results.length > 0 && (
        <div className="search-dropdown">
          {results.map(n => (
            <div
              key={n.pokemon_id}
              className="search-result"
              onMouseDown={() => {
                onSelect(n.pokemon_id);
                setQuery(n.name);
                setOpen(false);
              }}
            >
              <img src={n.sprite_url} alt={n.name} className="search-result-sprite" />
              <span className="search-result-name">{n.name}</span>
              <span className="search-result-id">#{n.pokemon_id}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
