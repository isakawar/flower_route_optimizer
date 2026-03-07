"use client";

import { Clock, Navigation, Hourglass, MapPin, GripVertical, Pencil } from "lucide-react";
import { formatMinutes } from "@/lib/utils";
import { COURIER_COLORS } from "@/types";
import type { CourierRoute } from "@/types";

export interface DragState {
  courierId: number;
  stopIdx: number;
}

export interface DropTarget {
  courierId: number;
  insertIdx: number; // insert BEFORE this index; stops.length = append at end
}

interface Props {
  route: CourierRoute;
  index: number;
  isHighlighted?: boolean;
  onHover?: (courierId: number | null) => void;
  onEditStop?: (courierId: number, stopIdx: number) => void;
  onDragStart?: (state: DragState) => void;
  onDragEnd?: () => void;
  onDragOverStop?: (target: DropTarget) => void;
  onDragOverCard?: (courierId: number) => void;
  onDrop?: () => void;
  dragging?: DragState | null;
  dropTarget?: DropTarget | null;
}

function DropLine({ active, color }: { active: boolean; color: string }) {
  return (
    <div
      className="mx-5 rounded-full transition-all duration-150"
      style={{
        height: active ? "2px" : "0px",
        background: color,
        opacity: active ? 1 : 0,
        marginTop: active ? "2px" : "0px",
        marginBottom: active ? "2px" : "0px",
      }}
    />
  );
}

export default function CourierCard({
  route,
  index,
  isHighlighted,
  onHover,
  onEditStop,
  onDragStart,
  onDragEnd,
  onDragOverStop,
  onDragOverCard,
  onDrop,
  dragging,
  dropTarget,
}: Props) {
  const color = COURIER_COLORS[index % COURIER_COLORS.length];
  const hasWaiting = route.stops.some((s) => s.waitMin > 0);
  const isBeingDraggedFrom = dragging?.courierId === route.courierId;

  const isDropZoneActive = (insertIdx: number) =>
    dropTarget?.courierId === route.courierId && dropTarget?.insertIdx === insertIdx;

  return (
    <div
      className={`card-base overflow-hidden transition-all duration-300 ${
        isHighlighted ? "shadow-card-hover" : "hover:shadow-card-hover"
      }`}
      style={isHighlighted ? { outline: `1.5px solid ${color}60` } : undefined}
      onMouseEnter={() => onHover?.(route.courierId)}
      onMouseLeave={() => onHover?.(null)}
      onDragOver={(e) => {
        e.preventDefault();
        onDragOverCard?.(route.courierId);
      }}
      onDrop={(e) => {
        e.preventDefault();
        onDrop?.();
      }}
    >
      {/* Card header */}
      <div className="px-5 py-4 flex items-center gap-3 border-b border-border/60">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center text-bg-deep text-sm font-bold flex-shrink-0"
          style={{ background: `linear-gradient(135deg, ${color}, ${color}99)` }}
        >
          {route.courierId}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-text-primary text-sm font-semibold">
            Кур&apos;єр {route.courierId}
          </p>
          <p className="text-text-muted text-xs">
            {route.stops.length}{" "}
            {route.stops.length === 1
              ? "зупинка"
              : route.stops.length < 5
              ? "зупинки"
              : "зупинок"}
          </p>
        </div>

        <div className="hidden sm:flex items-center gap-2">
          <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-bg-raised text-text-muted text-[11px]">
            <Clock size={10} />
            {formatMinutes(route.totalDriveMin)}
          </div>
          <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-bg-raised text-text-muted text-[11px]">
            <Navigation size={10} />
            {route.totalDistanceKm.toFixed(1)} км
          </div>
        </div>
      </div>

      {/* Stops */}
      <div>
        <DropLine active={isDropZoneActive(0)} color={color} />

        {route.stops.map((stop, stopIdx) => {
          const isDraggingThis =
            dragging?.courierId === route.courierId && dragging?.stopIdx === stopIdx;

          return (
            <div key={stopIdx}>
              <div
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.effectAllowed = "move";
                  onDragStart?.({ courierId: route.courierId, stopIdx });
                }}
                onDragEnd={() => onDragEnd?.()}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onDragOverStop?.({ courierId: route.courierId, insertIdx: stopIdx });
                }}
                className={`flex items-start gap-3 px-5 py-3.5 border-b border-border/30 last:border-0
                            transition-all duration-150 group/stop
                            ${isDraggingThis ? "opacity-40 bg-rose-glow/40" : "hover:bg-white/[0.02]"}
                            cursor-grab active:cursor-grabbing`}
              >
                {/* Drag handle */}
                <div className="flex-shrink-0 pt-0.5 text-text-muted opacity-0 group-hover/stop:opacity-50
                                transition-opacity select-none mt-0.5">
                  <GripVertical size={13} />
                </div>

                {/* Stop number + vertical connector */}
                <div className="flex flex-col items-center flex-shrink-0 mt-0.5">
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0"
                    style={{ background: `${color}33`, border: `1.5px solid ${color}66` }}
                  >
                    <span style={{ color }}>{stopIdx + 1}</span>
                  </div>
                  {stopIdx < route.stops.length - 1 && (
                    <div
                      className="w-px flex-1 mt-1 mb-1 min-h-[12px]"
                      style={{ background: `${color}22` }}
                    />
                  )}
                </div>

                {/* Stop details */}
                <div className="flex-1 min-w-0 pb-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-text-primary text-sm leading-snug flex-1 min-w-0 truncate">
                      {stop.address}
                    </p>
                    <span
                      className="text-xs font-semibold px-2 py-0.5 rounded-lg flex-shrink-0 tabular-nums"
                      style={{
                        background: `${color}15`,
                        color,
                        border: `1px solid ${color}30`,
                      }}
                    >
                      {stop.eta}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 mt-1.5">
                    <span className="flex items-center gap-1 text-text-muted text-[11px]">
                      <Navigation size={9} className="opacity-70" />
                      {stop.driveMin} хв їзди
                    </span>
                    {stop.waitMin > 0 && (
                      <span className="flex items-center gap-1 text-gold-soft/70 text-[11px]">
                        <Hourglass size={9} className="opacity-70" />
                        {stop.waitMin} хв очікування
                      </span>
                    )}
                  </div>
                </div>

                {/* Edit button */}
                <button
                  className="flex-shrink-0 p-1.5 rounded-lg text-text-muted opacity-0
                             group-hover/stop:opacity-100 hover:text-rose-soft hover:bg-rose-glow
                             transition-all duration-150"
                  onClick={(e) => {
                    e.stopPropagation();
                    onEditStop?.(route.courierId, stopIdx);
                  }}
                  title="Редагувати"
                >
                  <Pencil size={12} />
                </button>
              </div>

              <DropLine active={isDropZoneActive(stopIdx + 1)} color={color} />
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="px-5 py-3 bg-bg-raised/50 flex items-center justify-between border-t border-border/40">
        <div className="flex items-center gap-1 text-text-muted text-[11px]">
          <MapPin size={10} />
          <span>
            Перший вихід о{" "}
            <span className="text-text-secondary tabular-nums">{route.stops[0]?.eta}</span>
          </span>
        </div>
        {hasWaiting && (
          <div className="flex items-center gap-1 text-gold-soft/60 text-[11px]">
            <Hourglass size={10} />
            є очікування
          </div>
        )}
        {isBeingDraggedFrom && (
          <div className="flex items-center gap-1 text-rose-soft/50 text-[11px] animate-pulse">
            <GripVertical size={10} />
            перетягніть
          </div>
        )}
      </div>
    </div>
  );
}
