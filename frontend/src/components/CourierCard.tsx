"use client";

import { Clock, Navigation, Hourglass, MapPin } from "lucide-react";
import { formatMinutes } from "@/lib/utils";
import { COURIER_COLORS } from "@/types";
import type { CourierRoute } from "@/types";

interface Props {
  route: CourierRoute;
  index: number;
  isHighlighted?: boolean;
  onHover?: (courierId: number | null) => void;
}

export default function CourierCard({ route, index, isHighlighted, onHover }: Props) {
  const color = COURIER_COLORS[index % COURIER_COLORS.length];
  const hasWaiting = route.stops.some((s) => s.waitMin > 0);

  return (
    <div
      className={`card-base overflow-hidden transition-all duration-300 ${
        isHighlighted ? "shadow-card-hover" : "hover:shadow-card-hover"
      }`}
      style={isHighlighted ? { outline: `1.5px solid ${color}60` } : undefined}
      onMouseEnter={() => onHover?.(route.courierId)}
      onMouseLeave={() => onHover?.(null)}
    >
      {/* Card header */}
      <div className="px-5 py-4 flex items-center gap-3 border-b border-border/60">
        {/* Courier avatar */}
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

        {/* Route stats chips */}
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

      {/* Stops list */}
      <div className="divide-y divide-border/40">
        {route.stops.map((stop, stopIdx) => (
          <div key={stopIdx} className="flex items-start gap-3 px-5 py-3.5 group/stop hover:bg-white/[0.02] transition-colors">
            {/* Stop number with connector line */}
            <div className="flex flex-col items-center flex-shrink-0 mt-0.5">
              <div
                className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-bg-deep flex-shrink-0"
                style={{ background: `${color}33`, border: `1.5px solid ${color}66` }}
              >
                <span style={{ color }}>{stopIdx + 1}</span>
              </div>
              {stopIdx < route.stops.length - 1 && (
                <div className="w-px flex-1 mt-1 mb-1 min-h-[12px]" style={{ background: `${color}22` }} />
              )}
            </div>

            {/* Stop details */}
            <div className="flex-1 min-w-0 pb-1">
              <div className="flex items-start justify-between gap-2">
                <p className="text-text-primary text-sm leading-snug flex-1 min-w-0 truncate">
                  {stop.address}
                </p>
                {/* ETA badge */}
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

              {/* Metadata row */}
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
          </div>
        ))}
      </div>

      {/* Card footer */}
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
      </div>
    </div>
  );
}
