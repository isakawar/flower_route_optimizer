"use client";

import { Check } from "lucide-react";
import type { ProgressStep } from "@/types";

const STEP_ICONS: Record<string, React.ReactNode> = {
  upload: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points="17 8 12 3 7 8" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="12" y1="3" x2="12" y2="15" strokeLinecap="round" />
    </svg>
  ),
  geocode: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3" strokeLinecap="round" />
    </svg>
  ),
  matrix: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  ),
  optimize: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  finalize: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points="22 4 12 14.01 9 11.01" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
};

function FlowerSpinner() {
  return (
    <svg width="72" height="72" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Rotating petals group */}
      <g style={{ transformOrigin: "32px 32px", animation: "spin 6s linear infinite" }}>
        {Array.from({ length: 8 }).map((_, i) => {
          const angle = (i * 45 * Math.PI) / 180;
          const cx = 32 + 13 * Math.cos(angle);
          const cy = 32 + 13 * Math.sin(angle);
          return (
            <ellipse
              key={i}
              cx={cx}
              cy={cy}
              rx="4.5"
              ry="8"
              transform={`rotate(${i * 45}, ${cx}, ${cy})`}
              fill={i % 2 === 0 ? "rgba(212,165,191,0.6)" : "rgba(201,169,110,0.5)"}
              style={{ animation: `pulseSubtle 2s ease-in-out ${i * 0.25}s infinite` }}
            />
          );
        })}
      </g>

      {/* Centre */}
      <circle cx="32" cy="32" r="7" fill="#0a0a12" />
      <circle cx="32" cy="32" r="5.5" fill="#d4a5bf" opacity="0.9" />
      <circle cx="32" cy="32" r="3" fill="#c9a96e" opacity="0.95" />
      <circle cx="32" cy="32" r="1.5" fill="#0a0a12" />
    </svg>
  );
}

export default function ProgressUI({ steps }: { steps: ProgressStep[] }) {
  const completedCount = steps.filter((s) => s.status === "complete").length;
  const progress = (completedCount / steps.length) * 100;
  const activeStep = steps.find((s) => s.status === "active");

  return (
    <div className="max-w-md mx-auto py-12 flex flex-col items-center">
      {/* Spinner with glow ring */}
      <div className="relative mb-10">
        {/* Outer glow ring */}
        <div
          className="absolute inset-0 rounded-full border border-rose-soft/20 animate-spin-slow"
          style={{
            borderTopColor: "rgba(212,165,191,0.6)",
            borderRightColor: "rgba(201,169,110,0.3)",
          }}
        />
        {/* Second ring — counter-rotating */}
        <div
          className="absolute inset-2 rounded-full border border-gold-soft/10"
          style={{
            borderBottomColor: "rgba(201,169,110,0.4)",
            animation: "spin 4s linear infinite reverse",
          }}
        />
        <div className="w-24 h-24 flex items-center justify-center">
          <FlowerSpinner />
        </div>
        {/* Progress percentage */}
        <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 text-xs text-text-muted font-medium tabular-nums">
          {Math.round(progress)}%
        </div>
      </div>

      {/* Title */}
      <div className="mt-4 text-center mb-8">
        <h2 className="font-serif text-2xl text-text-primary mb-1">
          Оптимізуємо маршрути
        </h2>
        <p className="text-text-muted text-sm h-5 transition-all duration-300">
          {activeStep?.label ?? "Завершення…"}
        </p>
      </div>

      {/* Progress bar */}
      <div className="w-full h-1 bg-bg-raised rounded-full mb-8 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{
            width: `${progress}%`,
            background: "linear-gradient(90deg, #8a6a7e, #d4a5bf, #c9a96e)",
          }}
        />
      </div>

      {/* Steps list */}
      <div className="w-full space-y-2">
        {steps.map((step, idx) => (
          <div
            key={step.id}
            className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-all duration-500 ${
              step.status === "active"
                ? "border-rose-soft/25 bg-rose-glow"
                : step.status === "complete"
                ? "border-transparent bg-transparent"
                : "border-transparent bg-transparent opacity-40"
            }`}
          >
            {/* Step indicator */}
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300 ${
                step.status === "complete"
                  ? "bg-rose-soft/15 text-rose-soft"
                  : step.status === "active"
                  ? "bg-rose-soft/10 border border-rose-soft/50 text-rose-soft"
                  : "border border-border text-text-muted"
              }`}
            >
              {step.status === "complete" ? (
                <Check size={12} strokeWidth={2.5} />
              ) : (
                <span className={step.status === "active" ? "animate-pulse-subtle" : ""}>
                  {STEP_ICONS[step.id] ?? <span className="text-[10px]">{idx + 1}</span>}
                </span>
              )}
            </div>

            {/* Label */}
            <span
              className={`text-sm flex-1 transition-colors duration-300 ${
                step.status === "active"
                  ? "text-text-primary font-medium"
                  : step.status === "complete"
                  ? "text-text-secondary line-through decoration-text-muted"
                  : "text-text-muted"
              }`}
            >
              {step.label}
            </span>

            {/* Active dots */}
            {step.status === "active" && (
              <div className="flex gap-1 items-center">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-rose-soft animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            )}

            {/* Complete checkmark pulse */}
            {step.status === "complete" && (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-rose-soft/60 flex-shrink-0">
                <polyline points="20 6 9 17 4 12" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
