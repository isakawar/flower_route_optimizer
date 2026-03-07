import type { OptimizationParams, OptimizationResult, RecalculateParams } from "@/types";
import { MOCK_RESULT } from "./mockData";

export class InfeasibleError extends Error {
  readonly minimumCouriersRequired: number;
  readonly reason: string;
  constructor(message: string, minimum: number, reason = "unknown") {
    super(message);
    this.name = "InfeasibleError";
    this.minimumCouriersRequired = minimum;
    this.reason = reason;
  }
}

function parseApiError(body: Record<string, unknown>, status: number): Error {
  // Flat INFEASIBLE response (JSONResponse, no `detail` wrapper)
  if (status === 422 && body.error === "INFEASIBLE") {
    return new InfeasibleError(
      String(body.message ?? "Infeasible schedule"),
      Number(body.minimum_couriers_required ?? 1),
      String(body.reason ?? "unknown")
    );
  }
  // Standard FastAPI error: { detail: string | object }
  const detail = body?.detail;
  return new Error(typeof detail === "string" ? detail : `Server error ${status}`);
}

// Simulate progressive progress updates
export async function* runOptimization(
  params: OptimizationParams,
  onStep: (stepId: string) => void
): AsyncGenerator<OptimizationResult> {
  const steps = ["upload", "geocode", "matrix", "optimize", "finalize"];
  const delays = [800, 1400, 1800, 3000, 700];

  for (let i = 0; i < steps.length; i++) {
    await new Promise((r) => setTimeout(r, delays[i]));
    onStep(steps[i]);
  }

  // Try real API; throw on backend errors, fall back to mock only if unreachable
  let backendReachable = false;
  try {
    const formData = new FormData();
    formData.append("file", params.csvFile);
    formData.append("start_time", params.startTime);
    formData.append("num_couriers", params.numCouriers.toString());
    formData.append("capacity", params.capacity.toString());

    const res = await fetch("/api/optimize", {
      method: "POST",
      body: formData,
      signal: AbortSignal.timeout(60_000),
    });

    backendReachable = true; // got an HTTP response → backend is running

    if (res.ok) {
      const data = await res.json();
      yield data as OptimizationResult;
      return;
    }

    // Backend returned an error — surface it instead of silently using mock data
    const body = await res.json().catch(() => ({}));
    throw parseApiError(body, res.status);
  } catch (err) {
    if (backendReachable) {
      // Re-throw: backend is up but returned an error (bad CSV, no solution, etc.)
      throw err;
    }
    // Backend is not running — fall back to demo data so the UI is still usable
    console.info("[api] Backend unreachable — using demo data");
  }

  // Demo mode (no backend running)
  yield MOCK_RESULT;
}

export async function recalculate(params: RecalculateParams): Promise<OptimizationResult> {
  const res = await fetch("/api/recalculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal: AbortSignal.timeout(60_000),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw parseApiError(body, res.status);
  }
  return res.json();
}
