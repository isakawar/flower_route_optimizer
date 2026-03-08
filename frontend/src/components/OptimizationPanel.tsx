"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import {
  Upload,
  Clock,
  Users,
  Package,
  ChevronUp,
  ChevronDown,
  Flower2,
} from "lucide-react";
import type { OptimizationParams } from "@/types";

interface Props {
  onSubmit: (params: OptimizationParams) => void;
  isLoading: boolean;
}

function NumberStepper({
  value,
  onChange,
  min,
  max,
  label,
}: {
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  label: string;
}) {
  const [raw, setRaw] = useState(String(value));

  useEffect(() => {
    setRaw(String(value));
  }, [value]);

  const commit = (s: string) => {
    const v = parseInt(s);
    if (!isNaN(v) && v >= min && v <= max) {
      onChange(v);
    } else {
      setRaw(String(value)); // revert to last valid
    }
  };

  return (
    <div className="flex items-center gap-0 rounded-xl border border-border bg-bg-base overflow-hidden focus-within:border-rose-soft/40 transition-colors">
      <input
        type="number"
        value={raw}
        min={min}
        max={max}
        onChange={(e) => setRaw(e.target.value)}
        onBlur={(e) => commit(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && commit(raw)}
        aria-label={label}
        className="flex-1 bg-transparent px-4 py-3 text-sm text-text-primary text-center
                   outline-none placeholder-text-muted"
      />
      <div className="flex flex-col border-l border-border">
        <button
          type="button"
          onClick={() => value < max && onChange(value + 1)}
          className="px-2 py-1.5 text-text-secondary hover:text-rose-soft hover:bg-rose-glow transition-colors"
          aria-label="Increase"
        >
          <ChevronUp size={14} />
        </button>
        <button
          type="button"
          onClick={() => value > min && onChange(value - 1)}
          className="px-2 py-1.5 text-text-secondary hover:text-rose-soft hover:bg-rose-glow transition-colors border-t border-border"
          aria-label="Decrease"
        >
          <ChevronDown size={14} />
        </button>
      </div>
    </div>
  );
}

export default function OptimizationPanel({ onSubmit, isLoading }: Props) {
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [startTime, setStartTime] = useState("09:00");
  const [numCouriers, setNumCouriers] = useState(3);
  const [capacity, setCapacity] = useState(15);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((file: File) => {
    if (file.name.endsWith(".csv")) {
      setCsvFile(file);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!csvFile) return;
    onSubmit({ csvFile, startTime, numCouriers, capacity });
  };

  const canSubmit = !!csvFile && !isLoading;

  return (
    <section id="optimizer" className="relative">
      {/* Section header */}
      <div className="mb-8 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-rose-soft/20 bg-rose-glow text-rose-soft text-xs tracking-wider uppercase mb-4">
          <Flower2 size={12} />
          Оптимізація маршрутів
        </div>
        <h2 className="font-serif text-3xl sm:text-4xl font-medium text-text-primary mb-3">
          Розрахуйте{" "}
          <em className="text-gradient-rose not-italic">ідеальний</em> маршрут
        </h2>
        <p className="text-text-secondary max-w-lg mx-auto text-sm leading-relaxed">
          Завантажте CSV з адресами доставки, налаштуйте параметри —
          і отримайте оптимальний маршрут за секунди.
        </p>
      </div>

      <div className="max-w-2xl mx-auto">
        <form onSubmit={handleSubmit}>
          <div className="card-base p-6 sm:p-8 space-y-6">
            {/* File upload */}
            <div>
              <label className="block text-xs font-medium text-text-secondary uppercase tracking-wider mb-3">
                CSV файл з адресами
              </label>
              <div
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                className={`
                  relative flex flex-col items-center justify-center gap-3
                  rounded-2xl border-2 border-dashed cursor-pointer
                  transition-all duration-300 py-10 px-6
                  ${
                    isDragging
                      ? "border-rose-soft bg-rose-glow scale-[1.01]"
                      : csvFile
                      ? "border-rose-soft/40 bg-rose-glow/50"
                      : "border-border hover:border-rose-soft/30 hover:bg-rose-glow/30"
                  }
                `}
              >
                {/* Decorative circles */}
                <div className="absolute inset-0 overflow-hidden rounded-2xl pointer-events-none">
                  <div className="absolute -top-6 -right-6 w-24 h-24 rounded-full bg-rose-glow blur-2xl" />
                  <div className="absolute -bottom-6 -left-6 w-20 h-20 rounded-full bg-gold-glow blur-2xl" />
                </div>

                <div
                  className={`relative p-3 rounded-2xl transition-colors ${
                    csvFile ? "bg-rose-soft/20" : "bg-white/5"
                  }`}
                >
                  <Upload
                    size={24}
                    className={csvFile ? "text-rose-soft" : "text-text-muted"}
                  />
                </div>

                <div className="text-center relative">
                  {csvFile ? (
                    <>
                      <p className="text-sm font-medium text-rose-soft">
                        {csvFile.name}
                      </p>
                      <p className="text-xs text-text-muted mt-1">
                        {(csvFile.size / 1024).toFixed(1)} KB · Натисніть для
                        заміни
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="text-sm text-text-secondary">
                        Перетягніть CSV або{" "}
                        <span className="text-rose-soft underline underline-offset-2">
                          виберіть файл
                        </span>
                      </p>
                      <p className="text-xs text-text-muted mt-1">
                        Підтримується формат .csv
                      </p>
                    </>
                  )}
                </div>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                />
              </div>

              {/* CSV format hint */}
              <div className="mt-2 flex items-start gap-2 text-xs text-text-muted">
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="mt-0.5 shrink-0"
                >
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 16v-4M12 8h.01" strokeLinecap="round" />
                </svg>
                <span>Очікувані колонки: city, address, house, delivery_window_start, delivery_window_end</span>
              </div>
            </div>

            {/* Parameters grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {/* Start time */}
              <div>
                <label className="flex items-center gap-1.5 text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">
                  <Clock size={12} />
                  Час старту
                </label>
                <input
                  type="time"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  className="w-full rounded-xl border border-border bg-bg-base px-4 py-3
                             text-sm text-text-primary outline-none
                             focus:border-rose-soft/40 hover:border-border-accent
                             transition-colors [color-scheme:dark]"
                />
              </div>

              {/* Num couriers */}
              <div>
                <label className="flex items-center gap-1.5 text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">
                  <Users size={12} />
                  Кількість кур'єрів
                </label>
                <NumberStepper
                  value={numCouriers}
                  onChange={setNumCouriers}
                  min={1}
                  max={20}
                  label="Кількість кур'єрів"
                />
              </div>

              {/* Capacity */}
              <div>
                <label className="flex items-center gap-1.5 text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">
                  <Package size={12} />
                  Місткість
                </label>
                <NumberStepper
                  value={capacity}
                  onChange={setCapacity}
                  min={1}
                  max={100}
                  label="Місткість кур'єра"
                />
              </div>
            </div>

            {/* Submit button */}
            <button
              type="submit"
              disabled={!canSubmit}
              className={`
                relative w-full py-4 rounded-xl font-medium text-sm
                overflow-hidden transition-all duration-300
                ${
                  canSubmit
                    ? "bg-gradient-to-r from-rose-muted via-rose-soft to-gold-soft text-bg-deep shadow-rose-glow hover:shadow-[0_0_40px_rgba(212,165,191,0.25)] hover:scale-[1.01] active:scale-[0.99]"
                    : "bg-bg-raised text-text-muted cursor-not-allowed"
                }
              `}
            >
              {/* Shimmer effect */}
              {canSubmit && (
                <span className="absolute inset-0 shimmer-bg pointer-events-none" />
              )}
              <span className="relative flex items-center justify-center gap-2">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" strokeLinecap="round" />
                  <path d="M21 3v5h-5" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" strokeLinecap="round" />
                  <path d="M8 16H3v5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {!csvFile
                  ? "Завантажте CSV для початку"
                  : isLoading
                  ? "Обчислення..."
                  : "Розрахувати маршрути"}
              </span>
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
