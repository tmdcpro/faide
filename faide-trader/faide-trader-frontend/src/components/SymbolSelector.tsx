import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '@/lib/api';
import { X, Search, Loader2, ChevronDown } from 'lucide-react';

interface SymbolSelectorProps {
  exchange: string;
  selectedSymbols: string[];
  onChange: (symbols: string[]) => void;
  multiple?: boolean;
  placeholder?: string;
}

export function SymbolSelector({
  exchange,
  selectedSymbols,
  onChange,
  multiple = true,
  placeholder = 'Search symbols...',
}: SymbolSelectorProps) {
  const [allSymbols, setAllSymbols] = useState<string[]>([]);
  const [filteredSymbols, setFilteredSymbols] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load symbols when exchange changes
  useEffect(() => {
    if (!exchange) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setAllSymbols([]);

    api.listSymbols(exchange).then((res) => {
      if (!cancelled) {
        setAllSymbols(res.symbols);
        setFilteredSymbols(res.symbols);
        setLoading(false);
      }
    }).catch((e) => {
      if (!cancelled) {
        setError(e instanceof Error ? e.message : 'Failed to load symbols');
        setLoading(false);
      }
    });

    return () => { cancelled = true; };
  }, [exchange]);

  // Filter symbols based on search
  useEffect(() => {
    if (!search.trim()) {
      setFilteredSymbols(allSymbols);
    } else {
      const q = search.toUpperCase();
      setFilteredSymbols(
        allSymbols.filter((s) => s.toUpperCase().includes(q))
      );
    }
  }, [search, allSymbols]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleSelect = useCallback((symbol: string) => {
    if (multiple) {
      if (selectedSymbols.includes(symbol)) {
        onChange(selectedSymbols.filter((s) => s !== symbol));
      } else {
        onChange([...selectedSymbols, symbol]);
      }
    } else {
      onChange([symbol]);
      setIsOpen(false);
    }
    setSearch('');
    inputRef.current?.focus();
  }, [multiple, selectedSymbols, onChange]);

  const handleRemove = useCallback((symbol: string) => {
    onChange(selectedSymbols.filter((s) => s !== symbol));
  }, [selectedSymbols, onChange]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !search && selectedSymbols.length > 0) {
      onChange(selectedSymbols.slice(0, -1));
    }
    if (e.key === 'Escape') {
      setIsOpen(false);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      {/* Selected symbols + search input */}
      <div
        className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm flex flex-wrap items-center gap-1 cursor-text min-h-[38px]"
        onClick={() => { setIsOpen(true); inputRef.current?.focus(); }}
      >
        {selectedSymbols.map((sym) => (
          <span
            key={sym}
            className="inline-flex items-center gap-1 bg-blue-600/30 text-blue-300 text-xs px-2 py-0.5 rounded"
          >
            {sym}
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); handleRemove(sym); }}
              className="hover:text-white"
            >
              <X size={12} />
            </button>
          </span>
        ))}
        <div className="flex-1 flex items-center gap-1 min-w-[100px]">
          <Search size={14} className="text-gray-500 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setIsOpen(true); }}
            onFocus={() => setIsOpen(true)}
            onKeyDown={handleKeyDown}
            placeholder={selectedSymbols.length === 0 ? placeholder : ''}
            className="bg-transparent outline-none text-sm flex-1 min-w-0"
          />
        </div>
        <ChevronDown size={14} className="text-gray-500 shrink-0" />
      </div>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-50 mt-1 w-full bg-slate-700 border border-slate-600 rounded shadow-xl max-h-60 overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center py-4 text-gray-400 text-sm">
              <Loader2 size={16} className="animate-spin mr-2" />
              Loading symbols from {exchange}...
            </div>
          )}

          {error && (
            <div className="px-3 py-2 text-red-400 text-sm">{error}</div>
          )}

          {!loading && !error && filteredSymbols.length === 0 && (
            <div className="px-3 py-2 text-gray-400 text-sm">
              {search ? 'No symbols match your search' : 'No symbols available'}
            </div>
          )}

          {!loading && !error && filteredSymbols.slice(0, 200).map((sym) => {
            const isSelected = selectedSymbols.includes(sym);
            return (
              <button
                type="button"
                key={sym}
                onClick={() => handleSelect(sym)}
                className={`w-full text-left px-3 py-1.5 text-sm hover:bg-slate-600 transition-colors flex items-center justify-between ${
                  isSelected ? 'bg-blue-600/20 text-blue-300' : 'text-gray-200'
                }`}
              >
                <span>{sym}</span>
                {isSelected && <span className="text-blue-400 text-xs">selected</span>}
              </button>
            );
          })}

          {!loading && !error && filteredSymbols.length > 200 && (
            <div className="px-3 py-2 text-gray-500 text-xs text-center">
              Showing 200 of {filteredSymbols.length} results. Refine your search.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
