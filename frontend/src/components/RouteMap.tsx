"use client";

import dynamic from "next/dynamic";
import type { OptimizationResult } from "@/types";

const RouteMapClient = dynamic(() => import("./RouteMapClient"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-bg-card">
      <div className="flex flex-col items-center gap-3">
        <div
          className="w-8 h-8 rounded-full border border-rose-soft/20 animate-spin-slow"
          style={{ borderTopColor: "rgba(212,165,191,0.6)" }}
        />
        <span className="text-text-muted text-xs">Завантаження карти…</span>
      </div>
    </div>
  ),
});

interface Props {
  result: OptimizationResult;
  highlightedCourier: number | null;
}

export default function RouteMap({ result, highlightedCourier }: Props) {
  return (
    <section id="map" className="card-base overflow-hidden">
      {/* Map header */}
      <div className="px-5 py-4 border-b border-border/60 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-4 rounded-full bg-gradient-to-b from-rose-soft to-gold-soft" />
          <h3 className="text-text-primary text-sm font-semibold">Карта маршрутів</h3>
        </div>
        <div className="flex items-center gap-2 text-text-muted text-xs">
          <span className="w-2.5 h-2.5 rounded-full bg-gold-soft inline-block" />
          Депо
          <span className="ml-2 text-text-muted">· наведіть на кур&apos;єра для підсвітки</span>
        </div>
      </div>

      {/* Map container */}
      <div className="h-[420px] sm:h-[480px]">
        <RouteMapClient result={result} highlightedCourier={highlightedCourier} />
      </div>
    </section>
  );
}
