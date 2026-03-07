"use client";

import "leaflet/dist/leaflet.css";
import { useEffect } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Polyline,
  Popup,
  useMap,
} from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import { COURIER_COLORS } from "@/types";
import type { OptimizationResult } from "@/types";

function FitBounds({ bounds }: { bounds: LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds, { padding: [48, 48] });
  }, [map, bounds]);
  return null;
}

interface Props {
  result: OptimizationResult;
  highlightedCourier: number | null;
}

export default function RouteMapClient({ result, highlightedCourier }: Props) {
  const { depot, routes } = result;

  // Collect all coords to compute bounds
  const allCoords: [number, number][] = [[depot.lat, depot.lng]];
  routes.forEach((r) => {
    r.stops.forEach((s) => {
      if (s.lat !== undefined && s.lng !== undefined) {
        allCoords.push([s.lat, s.lng]);
      }
    });
  });

  const bounds: LatLngBoundsExpression = allCoords.length > 1 ? allCoords : [[depot.lat - 0.05, depot.lng - 0.05], [depot.lat + 0.05, depot.lng + 0.05]];

  return (
    <MapContainer
      center={[depot.lat, depot.lng]}
      zoom={12}
      style={{ height: "100%", width: "100%", background: "#0d0d1a" }}
      zoomControl
      scrollWheelZoom
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
        subdomains="abcd"
        maxZoom={20}
      />

      <FitBounds bounds={bounds} />

      {/* Courier routes & stop markers */}
      {routes.map((route, idx) => {
        const color = COURIER_COLORS[idx % COURIER_COLORS.length];
        const isHighlighted = highlightedCourier === route.courierId;
        const isOtherHighlighted = highlightedCourier !== null && !isHighlighted;

        // Route polyline: depot → stops
        const routeCoords: [number, number][] = [[depot.lat, depot.lng]];
        route.stops.forEach((s) => {
          if (s.lat !== undefined && s.lng !== undefined) {
            routeCoords.push([s.lat, s.lng]);
          }
        });

        return (
          <div key={route.courierId}>
            {/* Route line */}
            {routeCoords.length > 1 && (
              <Polyline
                positions={routeCoords}
                pathOptions={{
                  color,
                  weight: isHighlighted ? 3.5 : isOtherHighlighted ? 1.5 : 2.5,
                  opacity: isOtherHighlighted ? 0.25 : isHighlighted ? 1 : 0.7,
                  dashArray: undefined,
                }}
              />
            )}

            {/* Stop markers */}
            {route.stops.map((stop, stopIdx) => {
              if (stop.lat === undefined || stop.lng === undefined) return null;
              return (
                <CircleMarker
                  key={stopIdx}
                  center={[stop.lat, stop.lng]}
                  radius={isHighlighted ? 8 : 6}
                  pathOptions={{
                    color,
                    fillColor: color,
                    fillOpacity: isOtherHighlighted ? 0.2 : 0.85,
                    weight: 2,
                    opacity: isOtherHighlighted ? 0.2 : 1,
                  }}
                >
                  <Popup>
                    <div className="p-1">
                      <div className="text-xs font-semibold mb-1" style={{ color }}>
                        Кур&apos;єр {route.courierId} · Зупинка {stopIdx + 1}
                      </div>
                      <div className="text-xs leading-snug">{stop.address}</div>
                      <div className="flex gap-2 mt-1.5 text-[11px] opacity-70">
                        <span>ETA: {stop.eta}</span>
                        <span>·</span>
                        <span>{stop.driveMin} хв</span>
                        {stop.waitMin > 0 && (
                          <>
                            <span>·</span>
                            <span>очік. {stop.waitMin} хв</span>
                          </>
                        )}
                      </div>
                    </div>
                  </Popup>
                </CircleMarker>
              );
            })}
          </div>
        );
      })}

      {/* Depot marker */}
      <CircleMarker
        center={[depot.lat, depot.lng]}
        radius={10}
        pathOptions={{
          color: "#c9a96e",
          fillColor: "#c9a96e",
          fillOpacity: 0.9,
          weight: 2.5,
        }}
      >
        <Popup>
          <div className="text-xs font-semibold text-amber-300">Депо / Старт</div>
        </Popup>
      </CircleMarker>
    </MapContainer>
  );
}
