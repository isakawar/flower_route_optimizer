"use client";

import { useState, useCallback } from "react";
import Header from "@/components/Header";
import OptimizationPanel from "@/components/OptimizationPanel";
import ProgressUI from "@/components/ProgressUI";
import ResultsDashboard from "@/components/ResultsDashboard";
import { runOptimization } from "@/lib/api";
import { PROGRESS_STEPS } from "@/lib/mockData";
import type { AppState, OptimizationParams, OptimizationResult, ProgressStep } from "@/types";

export default function Home() {
  const [appState, setAppState] = useState<AppState>("idle");
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const [lastStartTime, setLastStartTime] = useState("09:00");
  const [steps, setSteps] = useState<ProgressStep[]>(
    PROGRESS_STEPS.map((s) => ({ ...s, status: "pending" as const }))
  );

  const handleSubmit = useCallback(async (params: OptimizationParams) => {
    const stepIds: string[] = PROGRESS_STEPS.map((s) => s.id);

    setLastStartTime(params.startTime);
    setAppState("loading");
    setResult(null);
    setSteps(PROGRESS_STEPS.map((s, i) => ({ ...s, status: i === 0 ? "active" : "pending" })));

    const handleStep = (completedId: string) => {
      const completedIdx = stepIds.indexOf(completedId);
      setSteps(
        PROGRESS_STEPS.map((s, i) => ({
          ...s,
          status:
            i <= completedIdx
              ? "complete"
              : i === completedIdx + 1
              ? "active"
              : "pending",
        }))
      );
    };

    try {
      const gen = runOptimization(params, handleStep);
      const { value: data } = await gen.next();

      if (data) {
        setSteps(PROGRESS_STEPS.map((s) => ({ ...s, status: "complete" })));
        // Short pause so user sees all steps complete before transition
        await new Promise((r) => setTimeout(r, 600));
        setResult(data);
        setAppState("complete");
      } else {
        setAppState("error");
      }
    } catch {
      setAppState("error");
    }
  }, []);

  const handleReset = useCallback(() => {
    setAppState("idle");
    setResult(null);
    setSteps(PROGRESS_STEPS.map((s) => ({ ...s, status: "pending" })));
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1">
        {/* Hero banner — only on idle */}
        {appState === "idle" && (
          <div className="relative overflow-hidden border-b border-border/50">
            {/* Background petals */}
            <div className="pointer-events-none absolute inset-0 overflow-hidden">
              <div className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-rose-soft/4 blur-3xl" />
              <div className="absolute -bottom-20 -left-20 w-80 h-80 rounded-full bg-gold-glow blur-3xl" />
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-rose-glow blur-3xl" />
            </div>

            <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pt-20 pb-16 text-center">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-gold-soft/20 bg-gold-glow text-gold-soft text-[11px] tracking-widest uppercase mb-6 animate-fade-up">
                <span className="w-1 h-1 rounded-full bg-gold-soft" />
                Маршрутизація доставки квітів
              </div>

              <h1 className="font-serif text-4xl sm:text-5xl lg:text-6xl font-medium text-text-primary mb-5 leading-tight animate-fade-up" style={{ animationDelay: "0.1s" }}>
                Ідеальний маршрут —{" "}
                <span className="text-gradient-rose italic">за секунди</span>
              </h1>

              <p className="text-text-secondary max-w-xl mx-auto leading-relaxed animate-fade-up" style={{ animationDelay: "0.2s" }}>
                Завантажте список адрес, задайте параметри — і алгоритм побудує
                оптимальний маршрут для кожного кур&apos;єра з урахуванням вікон доставки.
              </p>
            </div>
          </div>
        )}

        {/* Main content area */}
        <div className={`mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 ${appState === "idle" ? "py-16" : "py-12"}`}>
          {appState === "idle" && (
            <OptimizationPanel onSubmit={handleSubmit} isLoading={false} />
          )}

          {appState === "loading" && (
            <div className="animate-fade-up">
              <ProgressUI steps={steps} />
            </div>
          )}

          {appState === "complete" && result && (
            <div className="animate-fade-up">
              <ResultsDashboard result={result} startTime={lastStartTime} onReset={handleReset} />
            </div>
          )}

          {appState === "error" && (
            <div className="flex flex-col items-center justify-center py-32 text-center gap-6">
              <div className="w-16 h-16 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-red-400">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 8v4M12 16h.01" strokeLinecap="round" />
                </svg>
              </div>
              <div>
                <p className="text-text-primary font-medium mb-1">Помилка розрахунку</p>
                <p className="text-text-muted text-sm">Не вдалося завершити оптимізацію. Спробуйте ще раз.</p>
              </div>
              <button
                onClick={handleReset}
                className="px-6 py-3 rounded-xl border border-border text-text-secondary hover:text-text-primary hover:border-border-accent text-sm transition-all duration-200"
              >
                Спробувати знову
              </button>
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/50 py-6">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 flex items-center justify-between">
          <span className="text-text-muted text-xs">
            © 2024 <span className="text-text-secondary">Kvitkova Povnya</span>
          </span>
          <span className="text-text-muted text-xs">Route Optimizer v2</span>
        </div>
      </footer>
    </div>
  );
}
