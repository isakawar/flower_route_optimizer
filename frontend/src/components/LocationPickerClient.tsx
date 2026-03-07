"use client";

import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, Marker, useMapEvents, useMap } from "react-leaflet";
import L from "leaflet";

// SVG pin icon — avoids Next.js asset path issues with default Leaflet icons
const PIN_ICON = L.divIcon({
  html: `<svg width="28" height="40" viewBox="0 0 28 40" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M14 0C6.268 0 0 6.268 0 14c0 10.5 14 26 14 26S28 24.5 28 14C28 6.268 21.732 0 14 0z"
          fill="#d4a5bf" stroke="#0a0a12" stroke-width="1.5"/>
    <circle cx="14" cy="14" r="5" fill="white" opacity="0.9"/>
    <circle cx="14" cy="14" r="2.5" fill="#d4a5bf"/>
  </svg>`,
  className: "",
  iconSize: [28, 40],
  iconAnchor: [14, 40],
  popupAnchor: [0, -42],
});

function DraggableMarker({
  position,
  onMove,
}: {
  position: [number, number];
  onMove: (lat: number, lng: number) => void;
}) {
  const markerRef = useRef<L.Marker>(null);

  // Keep marker in sync when position prop changes externally
  useEffect(() => {
    markerRef.current?.setLatLng(position);
  }, [position]);

  return (
    <Marker
      ref={markerRef}
      position={position}
      icon={PIN_ICON}
      draggable
      eventHandlers={{
        dragend: () => {
          const pos = markerRef.current?.getLatLng();
          if (pos) onMove(pos.lat, pos.lng);
        },
      }}
    />
  );
}

function ClickToPlace({ onMove }: { onMove: (lat: number, lng: number) => void }) {
  useMapEvents({
    click: (e) => onMove(e.latlng.lat, e.latlng.lng),
  });
  return null;
}

function MapRecenter({ position }: { position: [number, number] }) {
  const map = useMap();
  useEffect(() => {
    map.panTo(position, { animate: true, duration: 0.4 });
  }, [map, position]);
  return null;
}

interface Props {
  lat: number;
  lng: number;
  onLocationSelect: (lat: number, lng: number) => void;
}

export default function LocationPickerClient({ lat, lng, onLocationSelect }: Props) {
  const position: [number, number] = [lat, lng];

  return (
    <MapContainer
      center={position}
      zoom={14}
      style={{ height: "100%", width: "100%", background: "#0d0d1a" }}
      zoomControl={false}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution=""
        subdomains="abcd"
        maxZoom={19}
      />
      <ClickToPlace onMove={onLocationSelect} />
      <DraggableMarker position={position} onMove={onLocationSelect} />
      <MapRecenter position={position} />
    </MapContainer>
  );
}
