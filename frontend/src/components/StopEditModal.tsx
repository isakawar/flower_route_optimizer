"use client";

import dynamic from "next/dynamic";
import { useState, useCallback } from "react";
import { X, AlertTriangle, MapPin } from "lucide-react";
import AddressAutocomplete from "./AddressAutocomplete";
import type { DeliveryStop, AddressSuggestion } from "@/types";

const LocationPickerClient = dynamic(() => import("./LocationPickerClient"), {
  ssr: false,
  loading: () => (
    <div className="h-full flex items-center justify-center bg-bg-raised">
      <div className="flex flex-col items-center gap-2">
        <div className="w-5 h-5 rounded-full border border-rose-soft/30 border-t-rose-soft animate-spin" />
        <span className="text-xs text-text-muted">Завантаження карти…</span>
      </div>
    </div>
  ),
});

function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number) {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

interface Props {
  stop: DeliveryStop;
  courierId: number;
  stopIdx: number;
  onSave: (updated: Partial<DeliveryStop>) => void;
  onClose: () => void;
}

export default function StopEditModal({ stop, courierId, stopIdx, onSave, onClose }: Props) {
  const [address, setAddress] = useState(stop.address);
  const [lat, setLat] = useState(stop.lat ?? 50.4501);
  const [lng, setLng] = useState(stop.lng ?? 30.5234);
  const [modified, setModified] = useState(false);
  const [distanceFromOriginal, setDistanceFromOriginal] = useState<number | null>(null);
  const [mapVisible, setMapVisible] = useState(true);

  const originalLat = stop.lat;
  const originalLng = stop.lng;

  const updateDistance = useCallback(
    (newLat: number, newLng: number) => {
      if (originalLat !== undefined && originalLng !== undefined) {
        setDistanceFromOriginal(haversineKm(originalLat, originalLng, newLat, newLng));
      }
    },
    [originalLat, originalLng]
  );

  const handleSuggestionSelect = useCallback(
    (s: AddressSuggestion) => {
      const shortName = s.displayName.split(",").slice(0, 3).join(",").trim();
      setAddress(shortName);
      setLat(s.lat);
      setLng(s.lng);
      setModified(true);
      updateDistance(s.lat, s.lng);
    },
    [updateDistance]
  );

  const handleMapPick = useCallback(
    (newLat: number, newLng: number) => {
      setLat(newLat);
      setLng(newLng);
      setModified(true);
      updateDistance(newLat, newLng);
    },
    [updateDistance]
  );

  const handleSave = () => {
    onSave({ address, lat, lng });
    onClose();
  };

  const isWarn = distanceFromOriginal !== null && distanceFromOriginal > 5;
  const isDanger = distanceFromOriginal !== null && distanceFromOriginal > 20;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[900] bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-[1000] flex items-center justify-center p-4 pointer-events-none">
        <div className="pointer-events-auto bg-bg-card border border-border rounded-2xl shadow-2xl
                        w-full max-w-lg flex flex-col max-h-[92vh]">

          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-border flex-shrink-0">
            <div>
              <h3 className="font-serif text-base font-semibold text-text-primary">
                Редагувати зупинку
              </h3>
              <p className="text-xs text-text-muted mt-0.5">
                Кур&apos;єр {courierId} · зупинка {stopIdx + 1} · {stop.eta}
              </p>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/5 transition-colors"
            >
              <X size={16} />
            </button>
          </div>

          {/* Scrollable body */}
          <div className="overflow-y-auto flex-1 px-6 py-5 space-y-5">

            {/* Current address (editable label) */}
            <div>
              <label className="text-[11px] font-medium text-text-secondary uppercase tracking-wider block mb-2">
                Адреса зупинки
              </label>
              <input
                type="text"
                value={address}
                onChange={(e) => { setAddress(e.target.value); setModified(true); }}
                className="w-full rounded-xl border border-border bg-bg-base px-4 py-2.5 text-sm
                           text-text-primary outline-none focus:border-rose-soft/40 transition-colors"
              />
            </div>

            {/* Autocomplete search */}
            <div>
              <label className="text-[11px] font-medium text-text-secondary uppercase tracking-wider block mb-2">
                Пошук нової адреси
              </label>
              <AddressAutocomplete
                onSelect={handleSuggestionSelect}
                placeholder="Введіть вулицю, місто…"
              />
            </div>

            {/* Confidence warning */}
            {isWarn && (
              <div
                className={`flex items-start gap-2 px-3 py-2.5 rounded-xl border text-sm ${
                  isDanger
                    ? "bg-red-500/10 border-red-500/30 text-red-400"
                    : "bg-yellow-500/10 border-yellow-500/30 text-yellow-400"
                }`}
              >
                <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                <span>
                  {isDanger
                    ? `Можливе некоректне місце — нова точка на ${distanceFromOriginal!.toFixed(0)} км від початкової`
                    : `Розташування змінено на ${distanceFromOriginal!.toFixed(1)} км від початкового`}
                </span>
              </div>
            )}

            {/* Coordinates */}
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="text-[11px] font-medium text-text-secondary uppercase tracking-wider block mb-2">
                  Широта
                </label>
                <div className="px-3 py-2.5 rounded-xl border border-border bg-bg-base/60 text-sm
                                text-text-secondary tabular-nums font-mono">
                  {lat.toFixed(6)}
                </div>
              </div>
              <div className="flex-1">
                <label className="text-[11px] font-medium text-text-secondary uppercase tracking-wider block mb-2">
                  Довгота
                </label>
                <div className="px-3 py-2.5 rounded-xl border border-border bg-bg-base/60 text-sm
                                text-text-secondary tabular-nums font-mono">
                  {lng.toFixed(6)}
                </div>
              </div>
            </div>

            {/* Map picker */}
            <div>
              <button
                className="flex items-center gap-2 text-[11px] font-medium text-text-secondary
                           uppercase tracking-wider mb-2 hover:text-rose-soft transition-colors w-full"
                onClick={() => setMapVisible((v) => !v)}
              >
                <MapPin size={11} />
                Вибрати на карті
                <span className="text-text-muted font-normal ml-1 normal-case tracking-normal">
                  (натисніть або перетягніть маркер)
                </span>
                <svg
                  width="12" height="12"
                  viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                  className={`ml-auto transition-transform duration-200 ${mapVisible ? "rotate-180" : ""}`}
                >
                  <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              {mapVisible && (
                <div className="h-52 rounded-xl overflow-hidden border border-border">
                  <LocationPickerClient lat={lat} lng={lng} onLocationSelect={handleMapPick} />
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between px-6 py-4 border-t border-border flex-shrink-0 gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl border border-border text-text-secondary
                         hover:text-text-primary text-sm transition-colors"
            >
              Скасувати
            </button>
            <button
              onClick={handleSave}
              disabled={!modified}
              className={`px-6 py-2.5 rounded-xl font-medium text-sm transition-all duration-200 ${
                modified
                  ? "bg-gradient-to-r from-rose-muted via-rose-soft to-gold-soft text-bg-deep hover:scale-[1.02] active:scale-[0.98]"
                  : "bg-bg-raised text-text-muted cursor-not-allowed"
              }`}
            >
              Зберегти зміни
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
