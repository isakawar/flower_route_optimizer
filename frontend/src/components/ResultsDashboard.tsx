"use client";

import { useState } from "react";
import { RotateCcw, Flower2 } from "lucide-react";
import StatsPanel from "./StatsPanel";
import CourierCard from "./CourierCard";
import RouteMap from "./RouteMap";
import { COURIER_COLORS } from "@/types";
import type { OptimizationResult } from "@/types";

interface Props {
  result: OptimizationResult;
  onReset: () => void;
}

export default function ResultsDashboard({ result, onReset }: Props) {
  const [highlightedCourier, setHighlightedCourier] = useState<number | null>(null);

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* Results header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-rose-soft/20 bg-rose-glow text-rose-soft text-[11px] tracking-widest uppercase mb-3">
            <Flower2 size={11} />
            Результати оптимізації
          </div>
          <h2 className="font-serif text-2xl sm:text-3xl font-medium text-text-primary">
            Маршрути{" "}
            <span className="text-gradient-rose">розраховані</span>
          </h2>
          <p className="text-text-muted text-sm mt-1">
            {result.routes.length} маршрутів · {result.stats.totalDeliveries} доставок
          </p>
        </div>

        <button
          onClick={onReset}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-border text-text-secondary hover:text-text-primary hover:border-border-accent text-sm transition-all duration-200 flex-shrink-0"
        >
          <RotateCcw size={14} />
          <span className="hidden sm:inline">Новий розрахунок</span>
        </button>
      </div>

      {/* Stats panel */}
      <StatsPanel stats={result.stats} />

      {/* Map */}
      <section id="map">
        <RouteMap result={result} highlightedCourier={highlightedCourier} />
      </section>

      {/* Courier cards */}
      <section id="results">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-1.5 h-4 rounded-full bg-gradient-to-b from-rose-soft to-gold-soft" />
          <h3 className="text-text-primary text-sm font-semibold">Маршрути кур&apos;єрів</h3>

          {/* Color legend */}
          <div className="ml-auto flex items-center gap-2 flex-wrap justify-end">
            {result.routes.map((route, idx) => (
              <button
                key={route.courierId}
                onMouseEnter={() => setHighlightedCourier(route.courierId)}
                onMouseLeave={() => setHighlightedCourier(null)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] text-text-muted hover:text-text-secondary transition-colors"
                style={{
                  background: `${COURIER_COLORS[idx % COURIER_COLORS.length]}18`,
                  border: `1px solid ${COURIER_COLORS[idx % COURIER_COLORS.length]}30`,
                }}
              >
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ background: COURIER_COLORS[idx % COURIER_COLORS.length] }}
                />
                Кур&apos;єр {route.courierId}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {result.routes.map((route, idx) => (
            <CourierCard
              key={route.courierId}
              route={route}
              index={idx}
              isHighlighted={highlightedCourier === route.courierId}
              onHover={setHighlightedCourier}
            />
          ))}
        </div>
      </section>

      {/* Bottom action */}
      <div className="flex justify-center pt-4 pb-2">
        <button
          onClick={onReset}
          className="group flex items-center gap-2 px-6 py-3 rounded-xl border border-border text-text-secondary hover:text-text-primary hover:border-border-accent text-sm transition-all duration-200"
        >
          <RotateCcw size={14} className="group-hover:rotate-180 transition-transform duration-300" />
          Розрахувати новий маршрут
        </button>
      </div>
    </div>
  );
}
