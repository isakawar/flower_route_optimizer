"use client";

import { useState, useCallback } from "react";
import { RotateCcw, Flower2, RefreshCw, Loader2, AlertTriangle } from "lucide-react";
import StatsPanel from "./StatsPanel";
import CourierCard from "./CourierCard";
import RouteMap from "./RouteMap";
import StopEditModal from "./StopEditModal";
import { COURIER_COLORS } from "@/types";
import type { OptimizationResult, DeliveryStop, RecalculateParams, RecalculateRoute } from "@/types";
import type { DragState, DropTarget } from "./CourierCard";
import { recalculate } from "@/lib/api";

interface Props {
  result: OptimizationResult;
  startTime: string;
  onReset: () => void;
}

function applyDragDrop(
  result: OptimizationResult,
  from: DragState,
  to: DropTarget
): OptimizationResult {
  const routes = result.routes.map((r) => ({ ...r, stops: [...r.stops] }));
  const fromRoute = routes.find((r) => r.courierId === from.courierId)!;
  const toRoute = routes.find((r) => r.courierId === to.courierId)!;

  const [movedStop] = fromRoute.stops.splice(from.stopIdx, 1);
  let insertIdx = to.insertIdx;
  if (from.courierId === to.courierId && from.stopIdx < to.insertIdx) {
    insertIdx--;
  }
  toRoute.stops.splice(insertIdx, 0, movedStop);

  const liveRoutes = routes.filter((r) => r.stops.length > 0);
  return {
    ...result,
    routes: liveRoutes,
    stats: {
      ...result.stats,
      numCouriers: liveRoutes.length,
      totalDeliveries: liveRoutes.reduce((s, r) => s + r.stops.length, 0),
    },
  };
}

export default function ResultsDashboard({ result, startTime, onReset }: Props) {
  const [highlightedCourier, setHighlightedCourier] = useState<number | null>(null);
  const [mutableResult, setMutableResult] = useState<OptimizationResult>(result);
  const [isDirty, setIsDirty] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [recalcError, setRecalcError] = useState<string | null>(null);
  const [editingStop, setEditingStop] = useState<{ courierId: number; stopIdx: number } | null>(null);
  const [dragging, setDragging] = useState<DragState | null>(null);
  const [dropTarget, setDropTarget] = useState<DropTarget | null>(null);

  const handleDragStart = useCallback((state: DragState) => {
    setDragging(state);
    setDropTarget(null);
  }, []);

  const handleDragEnd = useCallback(() => {
    setDragging(null);
    setDropTarget(null);
  }, []);

  const handleDragOverStop = useCallback((target: DropTarget) => {
    setDropTarget(target);
  }, []);

  const handleDragOverCard = useCallback(
    (courierId: number) => {
      setDropTarget((prev) => {
        const route = mutableResult.routes.find((r) => r.courierId === courierId);
        const insertIdx = route?.stops.length ?? 0;
        if (prev?.courierId === courierId && prev?.insertIdx === insertIdx) return prev;
        return { courierId, insertIdx };
      });
    },
    [mutableResult.routes]
  );

  const handleDrop = useCallback(() => {
    if (!dragging || !dropTarget) {
      setDragging(null);
      setDropTarget(null);
      return;
    }
    setMutableResult((prev) => applyDragDrop(prev, dragging, dropTarget));
    setIsDirty(true);
    setDragging(null);
    setDropTarget(null);
  }, [dragging, dropTarget]);

  const handleEditStop = useCallback((courierId: number, stopIdx: number) => {
    setEditingStop({ courierId, stopIdx });
  }, []);

  const handleSaveStop = useCallback(
    (updated: Partial<DeliveryStop>) => {
      if (!editingStop) return;
      setMutableResult((prev) => ({
        ...prev,
        routes: prev.routes.map((r) => {
          if (r.courierId !== editingStop.courierId) return r;
          return {
            ...r,
            stops: r.stops.map((s, i) => (i === editingStop.stopIdx ? { ...s, ...updated } : s)),
          };
        }),
      }));
      setIsDirty(true);
      setEditingStop(null);
    },
    [editingStop]
  );

  const handleRecalculate = useCallback(async () => {
    setRecalculating(true);
    setRecalcError(null);
    try {
      const routes: RecalculateRoute[] = mutableResult.routes.map((r) => ({
        courierId: r.courierId,
        stops: r.stops.map((s) => ({
          lat: s.lat ?? 0,
          lng: s.lng ?? 0,
          address: s.address,
          timeStart: s.timeStart ?? null,
          timeEnd: s.timeEnd ?? null,
        })),
      }));
      const params: RecalculateParams = {
        routes,
        depot: mutableResult.depot,
        startTime,
      };
      const newResult = await recalculate(params);
      setMutableResult(newResult);
      setIsDirty(false);
    } catch (err) {
      setRecalcError(err instanceof Error ? err.message : "Помилка перерахунку");
    } finally {
      setRecalculating(false);
    }
  }, [mutableResult, startTime]);

  const editingStopData = editingStop
    ? mutableResult.routes.find((r) => r.courierId === editingStop.courierId)?.stops[editingStop.stopIdx]
    : null;

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
            {mutableResult.routes.length} маршрутів · {mutableResult.stats.totalDeliveries} доставок
          </p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {isDirty && (
            <button
              onClick={handleRecalculate}
              disabled={recalculating}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200
                         bg-gradient-to-r from-rose-muted via-rose-soft to-gold-soft text-bg-deep
                         hover:scale-[1.02] active:scale-[0.98] disabled:opacity-60 disabled:cursor-not-allowed disabled:scale-100"
            >
              {recalculating ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              {recalculating ? "Перерахунок…" : "Перерахувати"}
            </button>
          )}
          <button
            onClick={onReset}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-border text-text-secondary hover:text-text-primary hover:border-border-accent text-sm transition-all duration-200"
          >
            <RotateCcw size={14} />
            <span className="hidden sm:inline">Новий розрахунок</span>
          </button>
        </div>
      </div>

      {recalcError && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl border border-red-500/30 bg-red-500/10 text-red-400 text-sm">
          <AlertTriangle size={14} className="flex-shrink-0" />
          {recalcError}
        </div>
      )}

      {/* Stats panel */}
      <StatsPanel stats={mutableResult.stats} />

      {/* Map */}
      <section id="map">
        <RouteMap result={mutableResult} highlightedCourier={highlightedCourier} />
      </section>

      {/* Courier cards */}
      <section id="results">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-1.5 h-4 rounded-full bg-gradient-to-b from-rose-soft to-gold-soft" />
          <h3 className="text-text-primary text-sm font-semibold">Маршрути кур&apos;єрів</h3>

          {isDirty && !recalculating && (
            <span className="text-[11px] text-gold-soft/70 px-2 py-0.5 rounded-full bg-gold-soft/10 border border-gold-soft/20">
              є зміни · потрібен перерахунок
            </span>
          )}

          {/* Color legend */}
          <div className="ml-auto flex items-center gap-2 flex-wrap justify-end">
            {mutableResult.routes.map((route, idx) => (
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
          {mutableResult.routes.map((route, idx) => (
            <CourierCard
              key={route.courierId}
              route={route}
              index={idx}
              isHighlighted={highlightedCourier === route.courierId}
              onHover={setHighlightedCourier}
              onEditStop={handleEditStop}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
              onDragOverStop={handleDragOverStop}
              onDragOverCard={handleDragOverCard}
              onDrop={handleDrop}
              dragging={dragging}
              dropTarget={dropTarget}
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

      {/* Edit stop modal */}
      {editingStop && editingStopData && (
        <StopEditModal
          stop={editingStopData}
          courierId={editingStop.courierId}
          stopIdx={editingStop.stopIdx}
          onSave={handleSaveStop}
          onClose={() => setEditingStop(null)}
        />
      )}
    </div>
  );
}
