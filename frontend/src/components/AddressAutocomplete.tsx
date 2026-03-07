"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type { AddressSuggestion } from "@/types";

interface NominatimResult {
  lat: string;
  lon: string;
  display_name: string;
  importance: number;
  address: {
    city?: string;
    town?: string;
    village?: string;
    state?: string;
    country?: string;
  };
}

interface Props {
  onSelect: (suggestion: AddressSuggestion) => void;
  placeholder?: string;
  initialValue?: string;
}

function ConfidenceDot({ importance }: { importance: number }) {
  const color =
    importance > 0.5 ? "bg-emerald-400" : importance > 0.3 ? "bg-yellow-400" : "bg-red-400";
  const label =
    importance > 0.5 ? "Висока впевненість" : importance > 0.3 ? "Середня" : "Низька впевненість";
  return (
    <div className="flex items-center gap-1 mt-1">
      <span className={`w-1.5 h-1.5 rounded-full ${color} flex-shrink-0`} />
      <span className="text-[10px] text-text-muted">{label}</span>
    </div>
  );
}

export default function AddressAutocomplete({ onSelect, placeholder, initialValue }: Props) {
  const [query, setQuery] = useState(initialValue ?? "");
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const containerRef = useRef<HTMLDivElement>(null);

  const search = useCallback(async (q: string) => {
    if (q.length < 3) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=5&addressdetails=1`,
        { headers: { "User-Agent": "FlowerRouteOptimizer/1.0" } }
      );
      const data: NominatimResult[] = await res.json();
      const mapped: AddressSuggestion[] = data.map((r) => ({
        displayName: r.display_name,
        city: r.address.city ?? r.address.town ?? r.address.village ?? "",
        region: r.address.state ?? "",
        country: r.address.country ?? "",
        lat: parseFloat(r.lat),
        lng: parseFloat(r.lon),
        importance: r.importance,
      }));
      setSuggestions(mapped);
      if (mapped.length > 0) setOpen(true);
    } catch {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(query), 500);
    return () => clearTimeout(debounceRef.current);
  }, [query, search]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSelect = (s: AddressSuggestion) => {
    setQuery(s.displayName.split(",")[0].trim());
    onSelect(s);
    setOpen(false);
  };

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          placeholder={placeholder ?? "Пошук адреси…"}
          className="w-full rounded-xl border border-border bg-bg-base px-4 py-2.5 pr-10 text-sm
                     text-text-primary outline-none focus:border-rose-soft/40 transition-colors"
        />
        {loading ? (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div className="w-3.5 h-3.5 rounded-full border border-rose-soft/30 border-t-rose-soft animate-spin" />
          </div>
        ) : (
          <svg
            width="14" height="14"
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" strokeLinecap="round" />
          </svg>
        )}
      </div>

      {open && suggestions.length > 0 && (
        <div className="absolute z-[2000] top-full left-0 right-0 mt-1.5 rounded-xl border border-border
                        bg-bg-card shadow-card overflow-hidden">
          {suggestions.map((s, i) => (
            <button
              key={i}
              className="w-full text-left px-4 py-3 hover:bg-bg-raised transition-colors
                         border-b border-border/40 last:border-0 group"
              onMouseDown={(e) => {
                e.preventDefault(); // don't blur input
                handleSelect(s);
              }}
            >
              <p className="text-sm text-text-primary truncate group-hover:text-rose-soft transition-colors">
                {s.displayName.split(",")[0].trim()}
              </p>
              <p className="text-xs text-text-muted mt-0.5 truncate">
                {[s.city, s.region, s.country].filter(Boolean).join(", ")}
              </p>
              <ConfidenceDot importance={s.importance} />
            </button>
          ))}
        </div>
      )}

      {open && !loading && suggestions.length === 0 && query.length >= 3 && (
        <div className="absolute z-[2000] top-full left-0 right-0 mt-1.5 rounded-xl border border-border
                        bg-bg-card shadow-card px-4 py-3 text-sm text-text-muted">
          Нічого не знайдено
        </div>
      )}
    </div>
  );
}
