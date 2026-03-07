import type { OptimizationParams, OptimizationResult } from "@/types";
import { MOCK_RESULT } from "./mockData";

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

  // Try real API first, fall back to mock
  try {
    const formData = new FormData();
    formData.append("file", params.csvFile);
    formData.append("start_time", params.startTime);
    formData.append("num_couriers", params.numCouriers.toString());
    formData.append("capacity", params.capacity.toString());

    const res = await fetch("/api/optimize", {
      method: "POST",
      body: formData,
      signal: AbortSignal.timeout(30_000),
    });

    if (res.ok) {
      const data = await res.json();
      yield data as OptimizationResult;
      return;
    }
  } catch {
    // Backend not available — use demo data
  }

  // Return mock data (demo mode)
  yield MOCK_RESULT;
}
